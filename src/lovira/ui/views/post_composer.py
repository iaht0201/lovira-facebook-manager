
"""
Lovira Workspace 2.0 - Post Composer
Compact Multi-Fanpage Publishing Workspace
Native PySide6 Desktop

Features:
- Multi-select Fanpage dropdown, searchable
- Compact layout, fixed submit footer
- Text, Photo, Video, Reels
- Local media and media library
- Async URL video downloading
- Per-page caption overrides
- Live simulated preview
- Vietnam timezone scheduling
- Confirmation before queue insertion
"""

import hashlib
import ipaddress
import logging
import threading
import uuid

from datetime import timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlparse

from PySide6.QtCore import (
    Qt, Signal, QPoint, QSize,
    QDate, QTime, QDateTime,
    QThread, QTimer, QSignalBlocker
)

from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QFrame,
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QDateTimeEdit,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QFileDialog,
    QDialog,
    QMessageBox,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)

from src.lovira.domain.composer import (
    ContentSnapshot,
    ContentType,
    PostComposerState,
    ScheduleMode,
)

from src.lovira.domain.timezone import (
    vn_now,
    create_vn_datetime,
    vn_datetime_to_utc_iso,
    validate_schedule_time,
)

from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository

from src.lovira.ui.widgets.simulated_preview import (
    SimulatedPostPreview,
)


logger = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png"}


# ==========================================================
# DESIGN SYSTEM
# ==========================================================

COMPOSER_STYLE = """
QWidget#composerRoot {
    background: #0D1627;
    color: #E9EFFA;
}

QWidget#composerCanvas,
QWidget#composerLeft {
    background: transparent;
}

QLabel#composerHint,
QLabel#composerTitle {
    background: transparent;
    border: none;
}

QLabel#composerTitle {
    font-size: 16px;
    font-weight: 700;
    color: #F4F7FF;
}

QLabel#composerHint {
    font-size: 11px;
    color: #A7B6CD;
}

QScrollArea#composerScroll {
    background: transparent;
    border: none;
}

QGroupBox#composerSection {
    background: #17243A;
    color: #EAF0FA;
    border: 1px solid #2D405C;
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 8px;
    font-size: 12px;
    font-weight: 600;
}

QGroupBox#composerSection::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0 5px;
    background: #17243A;
    color: #DFE8F7;
}

QWidget#composerRoot QLineEdit,
QWidget#composerRoot QTextEdit,
QWidget#composerRoot QComboBox,
QWidget#composerRoot QDateTimeEdit {
    background: #202F47;
    color: #F1F5FC;
    border: 1px solid #364A68;
    border-radius: 8px;
    padding: 5px 9px;
    selection-background-color: #6257E8;
}

QWidget#composerRoot QLineEdit:focus,
QWidget#composerRoot QTextEdit:focus,
QWidget#composerRoot QComboBox:focus,
QWidget#composerRoot QDateTimeEdit:focus {
    border-color: #8981FF;
}

QWidget#composerRoot QPushButton {
    background: #263752;
    color: #E4ECF9;
    border: 1px solid #374C6B;
    border-radius: 8px;
    padding: 0 10px;
    min-height: 32px;
    font-size: 12px;
}

QWidget#composerRoot QPushButton:hover {
    background: #344864;
}

QWidget#composerRoot QPushButton:disabled {
    color: #7889A3;
    background: #1C293D;
}

QWidget#composerRoot QPushButton#composerPrimary {
    background: #6257E8;
    color: white;
    border-color: #756AF5;
    font-weight: 700;
}

QWidget#composerRoot QPushButton#composerPrimary:hover {
    background: #756AF0;
}

QWidget#composerRoot QPushButton#composerLink {
    background: transparent;
    border-color: transparent;
    color: #BAB4FF;
    padding: 0 5px;
}

QFrame#composerFooter {
    background: #17243A;
    border-top: 1px solid #30435E;
}

QFrame#composerPreviewPane {
    background: #17243A;
    border: 1px solid #2D405C;
    border-radius: 10px;
}

QProgressBar#composerProgress {
    background: #1B2940;
    border: 0;
    border-radius: 4px;
    height: 8px;
}

QProgressBar#composerProgress::chunk {
    background: #6257E8;
    border-radius: 4px;
}

QSplitter::handle {
    background: transparent;
}
"""


POPUP_STYLE = """
QFrame#pagePopup {
    background: #19273E;
    border: 1px solid #405474;
    border-radius: 11px;
}

QFrame#pagePopup QLabel {
    background: transparent;
    color: #A9B8CE;
    font-size: 11px;
}

QFrame#pagePopup QLineEdit {
    background: #23344F;
    color: #FFFFFF;
    border: 1px solid #405474;
    border-radius: 8px;
    padding: 6px 9px;
}

QFrame#pagePopup QLineEdit:focus {
    border-color: #8178F5;
}

QFrame#pagePopup QListWidget {
    background: transparent;
    border: none;
    outline: none;
}

QFrame#pagePopup QCheckBox {
    background: transparent;
    color: #E4EBF7;
    spacing: 9px;
    padding: 4px;
}

QFrame#pagePopup QPushButton {
    background: #283A55;
    color: #E4EBF7;
    border: 1px solid #3A4D6C;
    border-radius: 7px;
    padding: 5px 9px;
}

QFrame#pagePopup QPushButton:hover {
    background: #344A6B;
}
"""


# ==========================================================
# FANPAGE MULTI-SELECT DROPDOWN
# ==========================================================

class FanpageMultiSelect(QWidget):
    """
    Dropdown chọn nhiều Fanpage.

    - Tìm theo tên hoặc Facebook Page ID
    - Chọn nhiều Page bằng checkbox
    - Chọn tất cả / Bỏ chọn
    - Giữ lựa chọn khi cập nhật danh sách
    - Chỉ chọn Page có trạng thái ready
    - Trả về internal Page ID
    """

    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._rows = []
        self._names = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.button = QPushButton("Chọn Fanpage  ▾")
        self.button.setFixedHeight(36)
        self.button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )
        self.button.clicked.connect(self._open)

        layout.addWidget(self.button)

        # Popup
        self.popup = QFrame(
            self,
            Qt.WindowType.Popup |
            Qt.WindowType.FramelessWindowHint
        )
        self.popup.setObjectName("pagePopup")
        self.popup.setStyleSheet(POPUP_STYLE)

        body = QVBoxLayout(self.popup)
        body.setContentsMargins(10, 10, 10, 10)
        body.setSpacing(7)

        # Search
        self.search = QLineEdit()
        self.search.setPlaceholderText(
            "Tìm tên hoặc ID Fanpage..."
        )
        self.search.setFixedHeight(34)
        self.search.textChanged.connect(self._filter)

        body.addWidget(self.search)

        # Bulk actions
        actions = QHBoxLayout()

        self.all_button = QPushButton("Chọn tất cả")
        self.none_button = QPushButton("Bỏ chọn")

        self.all_button.clicked.connect(
            lambda: self._set_visible(True)
        )
        self.none_button.clicked.connect(
            lambda: self._set_visible(False)
        )

        actions.addWidget(self.all_button)
        actions.addWidget(self.none_button)
        actions.addStretch()

        body.addLayout(actions)

        # List
        self.items = QListWidget()
        self.items.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.items.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.items.setFixedHeight(180)

        body.addWidget(self.items)

        # Footer
        foot = QHBoxLayout()

        self.count_label = QLabel("0 Page đã chọn")

        done = QPushButton("Xong")
        done.clicked.connect(self.popup.hide)

        foot.addWidget(self.count_label)
        foot.addStretch()
        foot.addWidget(done)

        body.addLayout(foot)

    def set_pages(self, pages: List[Dict[str, Any]]):
        """Nạp Page, bảo lưu lựa chọn còn hợp lệ."""

        old = set(self.selected_page_ids())

        self.items.clear()
        self._rows.clear()
        self._names.clear()

        for page in pages:
            pid = str(page["id"])
            name = str(page.get("name") or "Fanpage")
            fb_id = str(page.get("facebook_page_id") or "")
            status = str(page.get("status") or "ready")

            allowed = status == "ready"

            label = (
                f"{name} ({fb_id})" if fb_id else name
            )

            if not allowed:
                label += "  ·  Cần kiểm tra kết nối"

            item = QListWidgetItem()
            item.setSizeHint(QSize(10, 35))
            self.items.addItem(item)

            checkbox = QCheckBox(label)
            checkbox.setChecked(pid in old and allowed)
            checkbox.setEnabled(allowed)
            checkbox.setToolTip(label)

            checkbox.toggled.connect(self._notify)

            self.items.setItemWidget(item, checkbox)

            self._rows.append((
                pid,
                item,
                checkbox,
                label.casefold()
            ))

            self._names[pid] = name

        self._filter(self.search.text())
        self._display()

        if old != set(self.selected_page_ids()):
            self.selection_changed.emit()

    def selected_page_ids(self) -> List[str]:
        return [
            pid
            for pid, _, checkbox, _ in self._rows
            if checkbox.isChecked()
        ]

    def _filter(self, text: str):
        keyword = text.strip().casefold()
        visible = 0

        for _, item, _, searchable in self._rows:
            show = keyword in searchable
            item.setHidden(not show)
            visible += int(show)

        self.items.setFixedHeight(
            min(245, max(45, visible * 35 + 5))
        )

        self.all_button.setText(
            "Chọn kết quả" if keyword else "Chọn tất cả"
        )

        if self.popup.isVisible():
            self.popup.adjustSize()

    def _set_visible(self, checked: bool):
        for _, item, checkbox, _ in self._rows:
            if not item.isHidden() and checkbox.isEnabled():
                with QSignalBlocker(checkbox):
                    checkbox.setChecked(checked)

        self._notify()

    def select_all(self):
        self.search.clear()
        self._set_visible(True)

    def clear_selection(self):
        for _, _, checkbox, _ in self._rows:
            with QSignalBlocker(checkbox):
                checkbox.setChecked(False)

        self._notify()

    def _notify(self, *_):
        self._display()
        self.selection_changed.emit()

    def _display(self):
        selected = self.selected_page_ids()
        total = len(self._rows)

        if not selected:
            title = "Chọn Fanpage đích"
        elif len(selected) == 1:
            title = self._names.get(
                selected[0],
                "1 Fanpage"
            )
        else:
            title = f"{len(selected)} Fanpage đã chọn"

        self.button.setText(title + "  ▾")

        self.button.setToolTip(
            "\n".join(
                self._names.get(pid, pid)
                for pid in selected
            )
        )

        self.count_label.setText(
            f"Đã chọn {len(selected)}/{total} Page"
        )

    def _open(self):
        anchor = self.mapToGlobal(
            QPoint(0, self.height() + 4)
        )

        screen = (
            QApplication.screenAt(anchor)
            or QApplication.primaryScreen()
        )

        if screen is None:
            return

        bounds = screen.availableGeometry()

        width = min(
            max(self.width(), 325),
            max(200, bounds.width() - 16)
        )

        self.popup.setFixedWidth(width)
        self.popup.adjustSize()

        height = self.popup.sizeHint().height()

        x = max(
            bounds.left() + 8,
            min(
                anchor.x(),
                bounds.right() - width - 7
            )
        )

        y = anchor.y()

        if y + height > bounds.bottom() - 8:
            y = self.mapToGlobal(
                QPoint(0, -height - 4)
            ).y()

        y = max(bounds.top() + 8, y)

        self.popup.move(x, y)
        self.popup.show()
        self.search.setFocus()


# ==========================================================
# MEDIA LIBRARY PICKER
# ==========================================================

class MediaPickerSimpleDialog(QDialog):
    """Hộp thoại chọn media trong thư viện."""

    def __init__(self, media_repo, parent=None):
        super().__init__(parent)

        self.selected_asset = None
        self.setWindowTitle("Chọn media từ thư viện")
        self.resize(650, 420)

        layout = QVBoxLayout(self)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm tên file...")
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 3)

        self.table.setHorizontalHeaderLabels([
            "Tên file",
            "Nguồn",
            "Thời lượng"
        ])

        self.table.horizontalHeader().setSectionResizeMode(
            0,
            QHeaderView.ResizeMode.Stretch
        )

        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )

        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )

        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.table.verticalHeader().hide()
        layout.addWidget(self.table)

        self.assets = media_repo.list_media_assets(
            limit=500
        )

        self._visible = []

        self.search.textChanged.connect(self._filter)
        self.table.itemDoubleClicked.connect(
            lambda *_: self._choose()
        )

        self._filter("")

        row = QHBoxLayout()
        row.addStretch()

        cancel = QPushButton("Hủy")
        cancel.clicked.connect(self.reject)

        choose = QPushButton("Đính kèm")
        choose.clicked.connect(self._choose)

        row.addWidget(cancel)
        row.addWidget(choose)

        layout.addLayout(row)

    def _filter(self, text):
        needle = text.strip().casefold()

        self._visible = [
            asset for asset in self.assets
            if needle in Path(
                asset.get("local_path") or ""
            ).name.casefold()
        ]

        self.table.setRowCount(len(self._visible))

        for row, asset in enumerate(self._visible):
            path = Path(asset.get("local_path") or "")

            minutes, seconds = divmod(
                int(asset.get("duration") or 0),
                60
            )

            values = (
                path.name,
                asset.get("source_platform") or "-",
                f"{minutes:02}:{seconds:02}"
            )

            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(path))
                self.table.setItem(row, col, item)

    def _choose(self):
        index = self.table.currentRow()

        if index < 0 or index >= len(self._visible):
            QMessageBox.warning(
                self,
                "Chưa chọn",
                "Vui lòng chọn một file media."
            )
            return

        asset = self._visible[index]

        if not Path(
            asset.get("local_path") or ""
        ).is_file():
            QMessageBox.warning(
                self,
                "Thiếu file",
                "File đã bị xóa hoặc di chuyển."
            )
            return

        self.selected_asset = asset
        self.accept()


# ==========================================================
# BACKGROUND MEDIA WORKER
# ==========================================================

class MediaImportWorker(QThread):
    """Tải, kiểm tra và tính checksum media ngoài UI thread."""

    succeeded = Signal(dict)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(
        self,
        *,
        path=None,
        url=None,
        downloader=None,
        processor=None,
        output_dir=None,
    ):
        super().__init__()

        self.path = Path(path) if path else None
        self.url = url
        self.downloader = downloader
        self.processor = processor

        self.output_dir = Path(
            output_dir or (
                Path.home() / "Downloads" / "LoviraMedia"
            )
        )

        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            if self.url:
                if self.downloader is None:
                    from src.lovira.integrations.downloaders.video_downloader import (
                        VideoDownloader
                    )
                    self.downloader = VideoDownloader()

                path = Path(
                    self.downloader.download(
                        self.url,
                        output_dir=self.output_dir,
                        progress_callback=lambda p: self.progress.emit(
                            int(getattr(p, "percent", 0) or 0)
                        ),
                        is_cancelled=self._cancel.is_set,
                    )
                )
            else:
                path = self.path

            if self._cancel.is_set():
                return

            if (
                not path
                or not path.is_file()
                or path.stat().st_size <= 0
            ):
                raise ValueError(
                    "File không tồn tại hoặc bị rỗng."
                )

            suffix = path.suffix.lower()

            if suffix not in VIDEO_EXT | IMAGE_EXT:
                raise ValueError(
                    "Chỉ hỗ trợ MP4, MOV, AVI, MKV, "
                    "WEBM, JPG, JPEG, PNG."
                )

            digest = hashlib.sha256()

            with path.open("rb") as handle:
                while chunk := handle.read(1024 * 1024):
                    if self._cancel.is_set():
                        return

                    digest.update(chunk)

            duration = 0.0
            width = None
            height = None

            if (
                suffix in VIDEO_EXT
                and self.processor is not None
            ):
                try:
                    info = self.processor.inspect_video(path)

                    duration = float(
                        getattr(info, "duration", 0) or 0
                    )
                    width = getattr(info, "width", None)
                    height = getattr(info, "height", None)

                except Exception as exc:
                    logger.warning(
                        "Không đọc được metadata: %s",
                        exc
                    )

            if self._cancel.is_set():
                return

            self.succeeded.emit({
                "file_path": str(path),
                "filename": path.name,
                "checksum": digest.hexdigest(),
                "size_bytes": path.stat().st_size,
                "size_mb": path.stat().st_size / 1048576,
                "duration": duration,
                "width": width,
                "height": height,
                "platform": (
                    "url_download" if self.url else "local"
                ),
                "source_url": self.url,
            })

        except Exception as exc:
            self.failed.emit(str(exc))


# ==========================================================
# POST COMPOSER WORKSPACE
# ==========================================================

class PostComposerView(QWidget):

    publish_enqueued = Signal(list)

    def __init__(
        self,
        page_repo: PageRepository,
        queue_repo: PublishQueueRepository,
        media_repo: Optional[Any] = None,
        downloader: Optional[Any] = None,
        media_processor: Optional[Any] = None,
        download_dir: Optional[Path] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        self.page_repo = page_repo
        self.queue_repo = queue_repo
        self.media_repo = media_repo
        self.downloader = downloader
        self.media_processor = media_processor

        self.download_dir = Path(
            download_dir or (
                Path.home() / "Downloads" / "LoviraMedia"
            )
        )

        self.composer_state = PostComposerState()
        self.composer_state.content_type = ContentType.REELS

        self.attached_media = None
        self._page_names = {}
        self._page_status = {}
        self._worker = None
        self._submitting = False

        self.setObjectName("composerRoot")
        self.setStyleSheet(COMPOSER_STYLE)

        self._build_ui()

        # Debounced preview
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(200)
        self._preview_timer.timeout.connect(
            self._update_live_preview
        )

        self.reload_pages()
        self._update_summary()
        self._queue_preview()

        app = QApplication.instance()

        if app:
            app.aboutToQuit.connect(self._on_exit)

    # ======================================================
    # UI HELPERS
    # ======================================================

    @staticmethod
    def _label(text, title=False):
        label = QLabel(text)
        label.setObjectName(
            "composerTitle" if title else "composerHint"
        )
        label.setWordWrap(True)
        return label

    @staticmethod
    def _section(name):
        box = QGroupBox(name)
        box.setObjectName("composerSection")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(12, 14, 12, 11)
        layout.setSpacing(7)

        return box, layout

    # ======================================================
    # BUILD UI
    # ======================================================

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 9, 12, 9)

        self.splitter = QSplitter(
            Qt.Orientation.Horizontal
        )
        self.splitter.setChildrenCollapsible(False)
        root.addWidget(self.splitter)

        # Left: scrollable composer
        left = QWidget()
        left.setObjectName("composerLeft")

        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 6, 0)
        left_layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("composerScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        left_layout.addWidget(self.scroll, 1)

        canvas = QWidget()
        canvas.setObjectName("composerCanvas")

        form = QVBoxLayout(canvas)
        form.setContentsMargins(2, 3, 8, 9)
        form.setSpacing(9)

        self.scroll.setWidget(canvas)

        # ------------------------------------------
        # HEADER
        # ------------------------------------------

        header = QHBoxLayout()

        title_group = QVBoxLayout()
        title_group.setSpacing(2)

        title_group.addWidget(
            self._label("Soạn bài mới", title=True)
        )
        title_group.addWidget(
            self._label("Một nội dung - nhiều Fanpage")
        )

        header.addLayout(title_group)
        header.addStretch()

        preview_button = QPushButton("Xem trước")
        preview_button.clicked.connect(
            self._open_preview_dialog
        )
        header.addWidget(preview_button)

        form.addLayout(header)

        # ------------------------------------------
        # 1. FANPAGE DROPDOWN
        # ------------------------------------------

        box, group = self._section("1  Fanpage đích")

        page_row = QHBoxLayout()
        page_row.setSpacing(10)

        self.page_dropdown = FanpageMultiSelect(self)
        self.page_dropdown.selection_changed.connect(
            self._on_page_selection_changed
        )

        self.lbl_selected_count = self._label(
            "Đã chọn 0 Page"
        )

        page_row.addWidget(self.page_dropdown, 1)
        page_row.addWidget(self.lbl_selected_count)

        group.addLayout(page_row)
        form.addWidget(box)

        # ------------------------------------------
        # 2. CONTENT TYPE & MEDIA
        # ------------------------------------------

        box, group = self._section(
            "2  Loại bài & media"
        )

        type_row = QHBoxLayout()
        type_row.addWidget(self._label("Loại bài:"))

        self.cb_content_type = QComboBox()
        self.cb_content_type.addItems([
            "Reels",
            "Video",
            "Văn bản",
            "Hình ảnh",
        ])

        self.cb_content_type.setFixedHeight(35)
        self.cb_content_type.setMaximumWidth(210)
        self.cb_content_type.currentTextChanged.connect(
            self._on_content_type_changed
        )

        type_row.addWidget(self.cb_content_type)
        type_row.addStretch()
        group.addLayout(type_row)

        # Media buttons
        media_actions = QHBoxLayout()

        self.btn_upload_video = QPushButton(
            "Chọn từ máy"
        )
        self.btn_select_library = QPushButton(
            "Thư viện"
        )

        self.btn_upload_video.clicked.connect(
            self._pick_local_video_file
        )
        self.btn_select_library.clicked.connect(
            self._open_media_library_picker
        )

        media_actions.addWidget(self.btn_upload_video)
        media_actions.addWidget(self.btn_select_library)
        media_actions.addStretch()

        group.addLayout(media_actions)

        # Attached media
        info_row = QHBoxLayout()

        self.lbl_media_info = self._label(
            "Chưa đính kèm media"
        )

        self.btn_clear_media = QPushButton("Gỡ file")
        self.btn_clear_media.setObjectName("composerLink")
        self.btn_clear_media.clicked.connect(
            self._clear_attached_media
        )
        self.btn_clear_media.hide()

        info_row.addWidget(self.lbl_media_info, 1)
        info_row.addWidget(self.btn_clear_media)

        group.addLayout(info_row)

        # URL downloader
        url_row = QHBoxLayout()

        self.input_video_url = QLineEdit()
        self.input_video_url.setFixedHeight(35)
        self.input_video_url.setPlaceholderText(
            "Dán link TikTok / Douyin / Bilibili..."
        )
        self.input_video_url.returnPressed.connect(
            self._download_and_attach_url
        )

        self.btn_download_url = QPushButton("Tải link")
        self.btn_download_url.clicked.connect(
            self._download_and_attach_url
        )

        url_row.addWidget(self.input_video_url, 1)
        url_row.addWidget(self.btn_download_url)

        group.addLayout(url_row)

        # Download status
        status_row = QHBoxLayout()

        self.lbl_download_status = self._label("")
        self.lbl_download_status.hide()

        self.btn_cancel_download = QPushButton(
            "Hủy tải"
        )
        self.btn_cancel_download.clicked.connect(
            self._request_cancel
        )
        self.btn_cancel_download.hide()

        status_row.addWidget(
            self.lbl_download_status, 1
        )
        status_row.addWidget(self.btn_cancel_download)

        group.addLayout(status_row)

        self.download_progress = QProgressBar()
        self.download_progress.setObjectName(
            "composerProgress"
        )
        self.download_progress.setRange(0, 100)
        self.download_progress.setTextVisible(False)
        self.download_progress.hide()

        group.addWidget(self.download_progress)
        form.addWidget(box)

        # ------------------------------------------
        # 3. CAPTION
        # ------------------------------------------

        box, group = self._section(
            "3  Nội dung / caption"
        )

        tag_row = QHBoxLayout()
        tag_row.addWidget(self._label("Hashtag:"))

        for tag in ("#reels", "#review", "#viral"):
            button = QPushButton(tag)
            button.setObjectName("composerLink")

            button.clicked.connect(
                lambda _=False, t=tag:
                self._append_hashtag(t)
            )
            tag_row.addWidget(button)

        tag_row.addStretch()
        group.addLayout(tag_row)

        self.caption_input = QTextEdit()
        self.caption_input.setPlaceholderText(
            "Nhập caption bài đăng..."
        )
        self.caption_input.setMinimumHeight(104)
        self.caption_input.setMaximumHeight(160)
        self.caption_input.textChanged.connect(
            self._on_caption_changed
        )

        group.addWidget(self.caption_input)

        counter = QHBoxLayout()

        self.btn_overrides = QPushButton(
            "Caption riêng từng Page"
        )
        self.btn_overrides.setObjectName("composerLink")
        self.btn_overrides.clicked.connect(
            self._edit_page_captions
        )

        self.lbl_char_count = self._label(
            "0 ký tự · 0 hashtag"
        )

        counter.addWidget(self.btn_overrides)
        counter.addStretch()
        counter.addWidget(self.lbl_char_count)

        group.addLayout(counter)
        form.addWidget(box)

        # ------------------------------------------
        # 4. SCHEDULE
        # ------------------------------------------

        box, group = self._section(
            "4  Thời gian đăng"
        )

        self.chk_schedule = QCheckBox(
            "Hẹn giờ (cần chạy nền trên máy)"
        )
        self.chk_schedule.toggled.connect(
            self._on_schedule_toggled
        )

        group.addWidget(self.chk_schedule)

        self.schedule_picker_frame = QWidget()
        picker = QHBoxLayout(self.schedule_picker_frame)
        picker.setContentsMargins(0, 0, 0, 0)

        self.datetime_picker = QDateTimeEdit()
        self.datetime_picker.setFixedHeight(35)
        self.datetime_picker.setDisplayFormat(
            "dd/MM/yyyy HH:mm"
        )
        self.datetime_picker.setCalendarPopup(True)

        initial = vn_now() + timedelta(hours=1)

        self.datetime_picker.setDateTime(
            QDateTime(
                QDate(
                    initial.year,
                    initial.month,
                    initial.day
                ),
                QTime(
                    initial.hour,
                    initial.minute,
                    0
                )
            )
        )

        self.datetime_picker.dateTimeChanged.connect(
            self._on_datetime_changed
        )

        picker.addWidget(self.datetime_picker)
        picker.addStretch()

        group.addWidget(self.schedule_picker_frame)
        self.schedule_picker_frame.hide()

        self.lbl_schedule_summary = self._label(
            "Đăng ngay sau khi xác nhận"
        )

        group.addWidget(self.lbl_schedule_summary)
        form.addWidget(box)

        form.addStretch()

        # ------------------------------------------
        # FIXED FOOTER
        # ------------------------------------------

        footer = QFrame()
        footer.setObjectName("composerFooter")

        foot_layout = QHBoxLayout(footer)
        foot_layout.setContentsMargins(8, 8, 8, 4)

        self.lbl_summary_text = self._label(
            "0 Page · Reels · Đăng ngay"
        )
        foot_layout.addWidget(self.lbl_summary_text, 1)

        self.btn_submit = QPushButton(
            "Kiểm tra & đăng"
        )
        self.btn_submit.setObjectName("composerPrimary")
        self.btn_submit.clicked.connect(
            self._handle_submit
        )

        foot_layout.addWidget(self.btn_submit)
        left_layout.addWidget(footer)

        self.splitter.addWidget(left)

        # ------------------------------------------
        # RIGHT: LIVE PREVIEW
        # ------------------------------------------

        self.preview_pane = QFrame()
        self.preview_pane.setObjectName(
            "composerPreviewPane"
        )

        preview_layout = QVBoxLayout(
            self.preview_pane
        )
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(7)

        preview_layout.addWidget(
            self._label(
                "XEM TRƯỚC BÀI ĐĂNG (MÔ PHỎNG)"
            )
        )

        self.preview_widget = SimulatedPostPreview(
            self.preview_pane
        )

        preview_layout.addWidget(
            self.preview_widget, 1
        )

        self.splitter.addWidget(self.preview_pane)
        self.splitter.setSizes([760, 320])

    # ======================================================
    # PAGE MANAGEMENT
    # ======================================================

    def reload_pages(self):
        pages = self.page_repo.list_pages()

        self._page_names = {
            str(p["id"]): str(
                p.get("name") or p["id"]
            )
            for p in pages
        }

        self._page_status = {
            str(p["id"]): str(
                p.get("status") or "ready"
            )
            for p in pages
        }

        self.page_dropdown.set_pages(pages)
        self._on_page_selection_changed()

    def _get_selected_page_ids(self) -> List[str]:
        return self.page_dropdown.selected_page_ids()

    def _select_all_pages(self):
        self.page_dropdown.select_all()

    def _deselect_all_pages(self):
        self.page_dropdown.clear_selection()

    def _on_page_selection_changed(self, *_):
        self.composer_state.selected_page_ids = (
            self._get_selected_page_ids()
        )

        self._update_summary()
        self._queue_preview()

    # ======================================================
    # CONTENT TYPE
    # ======================================================

    def _on_content_type_changed(self, text):
        self.composer_state.content_type = {
            "Reels": ContentType.REELS,
            "Video": ContentType.VIDEO,
            "Văn bản": ContentType.TEXT,
            "Hình ảnh": ContentType.PHOTO,
        }[text]

        self._update_summary()
        self._queue_preview()

    # ======================================================
    # CAPTION
    # ======================================================

    def _append_hashtag(self, tag):
        cursor = self.caption_input.textCursor()

        before = cursor.position()
        original = self.caption_input.toPlainText()

        prefix = (
            " "
            if before > 0
            and not original[before - 1].isspace()
            else ""
        )

        cursor.insertText(prefix + tag + " ")
        self.caption_input.setFocus()

    def _on_caption_changed(self):
        text = self.caption_input.toPlainText()

        self.composer_state.general_caption = text

        count = sum(
            word.startswith("#") and len(word) > 1
            for word in text.split()
        )

        self.lbl_char_count.setText(
            f"{len(text)} ký tự · {count} hashtag"
        )

        self._queue_preview()

    def _edit_page_captions(self):
        ids = self._get_selected_page_ids()

        if not ids:
            QMessageBox.information(
                self,
                "Chưa chọn Page",
                "Hãy chọn Fanpage trước."
            )
            return

        edits = {}

        for pid in ids:
            override = (
                self.composer_state
                .page_overrides.get(pid)
            )
            edits[pid] = (
                override.caption_override if override else ""
            )

        dlg = QDialog(self)
        dlg.setWindowTitle(
            "Caption riêng cho Fanpage"
        )
        dlg.resize(500, 340)

        layout = QVBoxLayout(dlg)
        layout.addWidget(
            QLabel("Bỏ trống để sử dụng caption chung.")
        )

        selector = QComboBox()

        for pid in ids:
            selector.addItem(
                self._page_names.get(pid, pid),
                pid
            )

        layout.addWidget(selector)

        editor = QTextEdit()
        layout.addWidget(editor)

        active = [ids[0]]
        editor.setPlainText(edits[active[0]] or "")

        def select(index):
            edits[active[0]] = editor.toPlainText()
            active[0] = selector.itemData(index)
            editor.setPlainText(edits[active[0]] or "")

        selector.currentIndexChanged.connect(select)

        row = QHBoxLayout()
        row.addStretch()

        cancel = QPushButton("Hủy")
        cancel.clicked.connect(dlg.reject)

        accept = QPushButton("Lưu")
        accept.clicked.connect(dlg.accept)

        row.addWidget(cancel)
        row.addWidget(accept)

        layout.addLayout(row)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            edits[active[0]] = editor.toPlainText()

            for pid, value in edits.items():
                self.composer_state.set_override_caption(
                    pid,
                    value.strip() or None
                )

            self._queue_preview()

    # ======================================================
    # SCHEDULE
    # ======================================================

    def _vn_datetime(self):
        dt = self.datetime_picker.dateTime()

        date = dt.date()
        time = dt.time()

        return create_vn_datetime(
            date.year(),
            date.month(),
            date.day(),
            time.hour(),
            time.minute()
        )

    def _on_schedule_toggled(self, enabled):
        self.composer_state.toggle_schedule(enabled)
        self.schedule_picker_frame.setVisible(enabled)

        self._update_schedule_display()
        self._update_summary()

    def _on_datetime_changed(self, *_):
        self._update_schedule_display()

    def _update_schedule_display(self):
        if self.chk_schedule.isChecked():
            self.lbl_schedule_summary.setText(
                f"{self._vn_datetime():%H:%M %d/%m/%Y}"
                " (UTC+7) · Lịch trên máy"
            )
        else:
            self.lbl_schedule_summary.setText(
                "Đăng ngay sau khi xác nhận"
            )

    # ======================================================
    # SUMMARY
    # ======================================================

    def _update_submit_button_label(self):
        self.btn_submit.setText(
            "Kiểm tra lịch đăng"
            if self.chk_schedule.isChecked()
            else "Kiểm tra & đăng"
        )

        self.btn_submit.setEnabled(
            bool(self._get_selected_page_ids())
            and not self._submitting
            and self._worker is None
        )

    def _update_summary(self):
        ids = self._get_selected_page_ids()

        self.lbl_selected_count.setText(
            f"Đã chọn {len(ids)} Page"
        )

        mode = (
            "Hẹn giờ"
            if self.chk_schedule.isChecked()
            else "Đăng ngay"
        )

        self.lbl_summary_text.setText(
            f"{len(ids)} Page · "
            f"{self.cb_content_type.currentText()} · "
            f"{mode}"
        )

        self._update_submit_button_label()

    # ======================================================
    # PICK MEDIA FROM COMPUTER
    # ======================================================

    def _pick_local_video_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn ảnh hoặc video",
            str(self.download_dir),
            "Media (*.mp4 *.mov *.avi *.mkv "
            "*.webm *.jpg *.jpeg *.png)"
        )

        if path:
            self._start_worker(path=path)

    # ======================================================
    # PICK FROM LIBRARY
    # ======================================================

    def _open_media_library_picker(self):
        if not self.media_repo:
            QMessageBox.information(
                self,
                "Thư viện",
                "Chưa có thư viện media."
            )
            return

        dlg = MediaPickerSimpleDialog(
            self.media_repo, self
        )

        if (
            dlg.exec() == QDialog.DialogCode.Accepted
            and dlg.selected_asset
        ):
            asset = dlg.selected_asset

            self.attach_video_data({
                "file_path": asset["local_path"],
                "media_id": asset["id"],
                "checksum": asset.get("checksum"),
                "duration": asset.get("duration"),
            })

    # ======================================================
    # DOWNLOAD VIDEO FROM URL
    # ======================================================

    def _download_and_attach_url(self):
        url = self.input_video_url.text().strip()

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        if (
            parsed.scheme not in ("http", "https")
            or not hostname
        ):
            QMessageBox.warning(
                self,
                "Liên kết",
                "Cần liên kết HTTP(S) hợp lệ."
            )
            return

        # Chặn URL nội bộ cơ bản
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            address = None

        if (
            hostname.lower() == "localhost"
            or hostname.lower().endswith(".local")
            or (address and not address.is_global)
        ):
            QMessageBox.warning(
                self,
                "Liên kết",
                "Không hỗ trợ địa chỉ mạng nội bộ."
            )
            return

        self._start_worker(url=url)

    # ======================================================
    # BACKGROUND WORKER
    # ======================================================

    def _start_worker(self, *, path=None, url=None):
        if self._worker is not None:
            return

        worker = MediaImportWorker(
            path=path,
            url=url,
            downloader=self.downloader,
            processor=self.media_processor,
            output_dir=self.download_dir,
        )

        self._worker = worker

        worker.progress.connect(
            self.download_progress.setValue
        )
        worker.succeeded.connect(self._media_loaded)
        worker.failed.connect(self._media_failed)
        worker.finished.connect(self._media_finished)
        worker.finished.connect(worker.deleteLater)

        self.lbl_download_status.setText(
            "Đang xử lý media..."
        )
        self.lbl_download_status.show()

        self.download_progress.setValue(0)
        self.download_progress.show()

        self.btn_cancel_download.show()
        self.btn_cancel_download.setEnabled(True)

        for button in (
            self.btn_upload_video,
            self.btn_select_library,
            self.btn_download_url,
        ):
            button.setEnabled(False)

        self._update_submit_button_label()
        worker.start()

    def _request_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

            self.lbl_download_status.setText(
                "Đang dừng tải..."
            )
            self.btn_cancel_download.setEnabled(False)

    def _media_loaded(self, data):
        if self.media_repo:
            try:
                data["media_id"] = (
                    self.media_repo.add_media_asset(
                        local_path=Path(data["file_path"]),
                        checksum=data["checksum"],
                        size_bytes=data["size_bytes"],
                        duration=data["duration"],
                        source_platform=data["platform"],
                        source_url=data["source_url"],
                        width=data["width"],
                        height=data["height"],
                    )
                )

            except Exception as exc:
                logger.warning(
                    "Không lưu được vào thư viện: %s",
                    exc
                )

                self.lbl_download_status.setText(
                    "File đã có nhưng chưa lưu được "
                    "vào thư viện."
                )

        self.attach_video_data(data)

        if data.get("source_url"):
            self.input_video_url.clear()

        if data.get("media_id"):
            self.lbl_download_status.setText(
                "Đã tải và thêm vào thư viện."
            )
        else:
            self.lbl_download_status.setText(
                "Đã đính kèm file."
            )

    def _media_failed(self, message):
        self.lbl_download_status.setText(
            "Lỗi: " + message
        )

        QMessageBox.warning(
            self,
            "Lỗi xử lý media",
            message
        )

    def _media_finished(self):
        self._worker = None

        self.btn_cancel_download.hide()
        self.download_progress.hide()

        for button in (
            self.btn_upload_video,
            self.btn_select_library,
            self.btn_download_url,
        ):
            button.setEnabled(True)

        self._update_submit_button_label()

    # ======================================================
    # ATTACH MEDIA
    # ======================================================

    def attach_video_data(
        self,
        data: Dict[str, Any]
    ):
        """
        Tương thích với Video Workspace.
        Nhận cả video và ảnh.
        """

        path = Path(data.get("file_path") or "")

        if (
            not path.is_file()
            or path.suffix.lower()
            not in VIDEO_EXT | IMAGE_EXT
        ):
            QMessageBox.warning(
                self,
                "Media",
                "Không tìm thấy file hoặc định dạng "
                "không hỗ trợ."
            )
            return

        self.attached_media = dict(data)
        self.attached_media["file_path"] = str(path)

        size_mb = path.stat().st_size / 1048576

        self.lbl_media_info.setText(
            f"{path.name} · {size_mb:.1f} MB"
        )
        self.lbl_media_info.setToolTip(str(path))

        self.btn_clear_media.show()

        if path.suffix.lower() in IMAGE_EXT:
            self.cb_content_type.setCurrentText(
                "Hình ảnh"
            )

        elif self.cb_content_type.currentText() in (
            "Văn bản", "Hình ảnh"
        ):
            self.cb_content_type.setCurrentText(
                "Reels"
            )

        if not self.caption_input.toPlainText().strip():
            suggestion = (
                data.get("caption")
                or data.get("title")
            )

            if suggestion:
                self.caption_input.setPlainText(
                    str(suggestion)
                )

        self._update_summary()
        self._queue_preview()

    def _clear_attached_media(self):
        self.attached_media = None

        self.lbl_media_info.setText(
            "Chưa đính kèm media"
        )
        self.lbl_media_info.setToolTip("")

        self.btn_clear_media.hide()
        self._queue_preview()

    # ======================================================
    # LIVE PREVIEW
    # ======================================================

    def _queue_preview(self):
        if hasattr(self, "_preview_timer"):
            self._preview_timer.start()

    def _preview_values(self):
        ids = self._get_selected_page_ids()
        pid = ids[0] if ids else None

        return {
            "page_name": self._page_names.get(
                pid, "Fanpage"
            ),
            "caption": (
                self.composer_state.get_effective_caption(pid)
                if pid
                else self.caption_input.toPlainText()
            ),
            "media_path": (
                self.attached_media.get("file_path")
                if self.attached_media
                else None
            ),
            "content_type": (
                self.cb_content_type.currentText()
            ),
        }

    def _update_live_preview(self):
        try:
            self.preview_widget.update_preview(
                **self._preview_values()
            )

        except Exception as exc:
            logger.warning(
                "Preview gặp lỗi: %s",
                exc
            )

    def _open_preview_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(
            "Xem trước bài đăng (mô phỏng)"
        )
        dlg.resize(410, 680)

        layout = QVBoxLayout(dlg)

        widget = SimulatedPostPreview(dlg)
        layout.addWidget(widget, 1)

        widget.update_preview(
            **self._preview_values()
        )

        close = QPushButton("Đóng")
        close.clicked.connect(dlg.accept)
        layout.addWidget(close)

        dlg.exec()

    # ======================================================
    # RESPONSIVE PREVIEW
    # ======================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "preview_pane"):
            if self.width() < 960:
                self.preview_pane.hide()
            elif self.width() > 1040:
                self.preview_pane.show()

    # ======================================================
    # WORKER SHUTDOWN
    # ======================================================

    def _on_exit(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()

            if not self._worker.wait(10000):
                logger.warning(
                    "Media worker chưa dừng. "
                    "Shell cần đợi thread hoàn tất "
                    "trước khi hủy view."
                )

    # ======================================================
    # VALIDATION & SUBMIT
    # ======================================================

    def _handle_submit(self):
        if self._submitting or self._worker is not None:
            return

        ids = self._get_selected_page_ids()

        if not ids:
            QMessageBox.warning(
                self,
                "Chưa chọn Page",
                "Vui lòng chọn ít nhất một Fanpage."
            )
            return

        not_ready = [
            pid for pid in ids
            if self._page_status.get(pid) != "ready"
        ]

        if not_ready:
            QMessageBox.warning(
                self,
                "Fanpage chưa sẵn sàng",
                "Một số Page chưa được xác minh quyền. "
                "Hãy kiểm tra lại kết nối."
            )
            return

        ctype = self.composer_state.content_type

        captions = {
            pid: self.composer_state
                .get_effective_caption(pid)
                .strip()
            for pid in ids
        }

        media = self.attached_media

        suffix = (
            Path(media["file_path"]).suffix.lower()
            if media
            else ""
        )

        # Validate text
        if ctype == ContentType.TEXT:
            if media or any(
                not text for text in captions.values()
            ):
                QMessageBox.warning(
                    self,
                    "Bài văn bản",
                    "Bài văn bản cần caption cho từng Page "
                    "và không đính kèm media."
                )
                return

        # Validate video
        if ctype in (
            ContentType.REELS,
            ContentType.VIDEO,
        ):
            if suffix not in VIDEO_EXT:
                QMessageBox.warning(
                    self,
                    "Thiếu video",
                    "Vui lòng đính kèm một file video "
                    "hợp lệ."
                )
                return

        # Validate photo
        if ctype == ContentType.PHOTO:
            if suffix not in IMAGE_EXT:
                QMessageBox.warning(
                    self,
                    "Thiếu ảnh",
                    "Vui lòng đính kèm ảnh JPG hoặc PNG."
                )
                return

        # Validate media path
        if media and not Path(
            media["file_path"]
        ).is_file():
            QMessageBox.warning(
                self,
                "File không tồn tại",
                "Media đã bị xóa hoặc di chuyển."
            )
            return

        # Validate schedule time
        is_scheduled = self.chk_schedule.isChecked()

        if is_scheduled:
            date_vn = self._vn_datetime()

            valid, reason = validate_schedule_time(
                date_vn
            )

            if not valid:
                QMessageBox.warning(
                    self,
                    "Giờ hẹn không hợp lệ",
                    reason
                )
                return

            scheduled_utc = vn_datetime_to_utc_iso(
                date_vn
            )

            when = (
                f"{date_vn:%H:%M %d/%m/%Y} (UTC+7)"
                " - lịch trên máy"
            )

        else:
            scheduled_utc = vn_datetime_to_utc_iso(
                vn_now()
            )
            when = "Đăng ngay sau khi tạo hàng đợi"

        # Confirmation
        names = "\n".join(
            "• " + self._page_names.get(pid, pid)
            for pid in ids[:8]
        )

        if len(ids) > 8:
            names += (
                f"\n... và {len(ids) - 8} Fanpage khác"
            )

        media_name = (
            Path(media["file_path"]).name
            if media else "Không"
        )

        confirmation = (
            f"Loại: {self.cb_content_type.currentText()}\n"
            f"Số Page: {len(ids)}\n"
            f"{names}\n\n"
            f"Media: {media_name}\n"
            f"Giờ: {when}\n\n"
            f"Tạo {len(ids)} tác vụ đăng bài?"
        )

        reply = QMessageBox.question(
            self,
            "Xác nhận trước khi đăng",
            confirmation,
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Lock submission
        self._submitting = True
        self._update_submit_button_label()

        try:
            batch_id = (
                "batch_" + uuid.uuid4().hex[:12]
            )

            request_id = (
                "composer_" + uuid.uuid4().hex[:16]
            )

            snapshots = []

            for pid in ids:
                snapshots.append(
                    ContentSnapshot(
                        batch_id=batch_id,
                        page_id=pid,
                        content_type=ctype,
                        final_caption=captions[pid],
                        primary_media_id=(
                            media.get("media_id")
                            if media else None
                        ),
                        media_checksum=(
                            media.get("checksum")
                            if media else None
                        ),
                        media_path=(
                            media.get("file_path")
                            if media else None
                        ),
                        scheduled_at_utc=scheduled_utc,
                        schedule_mode=ScheduleMode.LOCAL,
                    )
                )

            jobs = self.queue_repo.enqueue_batch(
                request_id,
                snapshots,
            )

            if not jobs:
                raise RuntimeError(
                    "Không tạo được tác vụ nào."
                )

            self.publish_enqueued.emit(jobs)

            QMessageBox.information(
                self,
                "Đã thêm vào hàng đợi",
                f"Đã tạo {len(jobs)} tác vụ.\n"
                "Xem tiến độ ở mục Lịch đăng.\n\n"
                "Thông báo này không có nghĩa là bài "
                "đã xuất bản lên Facebook."
            )

            # Reset content after enqueue
            self.caption_input.clear()
            self.composer_state.page_overrides.clear()
            self._clear_attached_media()
            self._queue_preview()

        except Exception as exc:
            logger.exception(
                "Không thêm được vào hàng đợi"
            )

            QMessageBox.critical(
                self,
                "Lỗi tạo tác vụ",
                str(exc)
            )

        finally:
            self._submitting = False
            self._update_submit_button_label()

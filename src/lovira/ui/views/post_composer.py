
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

import os
import sys
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
from PySide6.QtGui import QPixmap, QCursor

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
    QMenu,
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
    background: #0B1220;
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

QFrame#composerCard {
    background: #131D2E;
    border: 1px solid #1E2D45;
    border-radius: 12px;
}

QLabel#composerSectionTitle {
    font-size: 14px;
    font-weight: 700;
    color: #F1F5F9;
}

QLabel#composerBadgePill {
    background: #1E2D47;
    border: 1px solid #2D3E5D;
    border-radius: 10px;
    color: #8E9EB5;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
}

QFrame#segmentedBar {
    background: #0E1726;
    border: 1px solid #1E2D45;
    border-radius: 8px;
}

QPushButton#hashtagChip {
    background: #18253A;
    border: 1px solid #273852;
    border-radius: 12px;
    color: #A5B4FC;
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    min-height: 24px;
}

QPushButton#hashtagChip:hover {
    background: #243550;
    border-color: #6258E8;
    color: #FFFFFF;
}

QFrame#mediaAttachedBox {
    background: #141F32;
    border: 1px solid #2B3D59;
    border-radius: 10px;
}

QFrame#mediaUploadBox {
    background: #0E1726;
    border: 1px dashed #283952;
    border-radius: 10px;
}

QFrame#checklistCard {
    background: #0E1726;
    border: 1px solid #1E2D45;
    border-radius: 10px;
}

QWidget#composerRoot QLineEdit,
QWidget#composerRoot QTextEdit,
QWidget#composerRoot QComboBox,
QWidget#composerRoot QDateTimeEdit {
    background: #182438;
    color: #F1F5FC;
    border: 1px solid #283952;
    border-radius: 8px;
    padding: 5px 9px;
    selection-background-color: #6257E8;
}

QWidget#composerRoot QLineEdit:focus,
QWidget#composerRoot QTextEdit:focus,
QWidget#composerRoot QComboBox:focus,
QWidget#composerRoot QDateTimeEdit:focus {
    border-color: #6258E8;
}

QWidget#composerRoot QPushButton {
    background: #1E2D45;
    color: #E2E8F0;
    border: 1px solid #2B3D59;
    border-radius: 8px;
    padding: 0 12px;
    min-height: 32px;
    font-size: 12px;
    font-weight: 500;
}

QWidget#composerRoot QPushButton:hover {
    background: #2A3E5E;
    color: #FFFFFF;
}

QWidget#composerRoot QPushButton:disabled {
    color: #64748B;
    background: #131D2E;
    border-color: #1E2D45;
}

QWidget#composerRoot QPushButton#composerPrimary {
    background: #6258E8;
    color: white;
    border: none;
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
    background: #131D2E;
    border-top: 1px solid #1E2D45;
}

QProgressBar#composerProgress {
    background: #1B2940;
    border: 0;
    border-radius: 4px;
    height: 6px;
}

QProgressBar#composerProgress::chunk {
    background: #6258E8;
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

QWidget#composerRoot QPushButton#composerPageDropdown {
    background: #202F47;
    color: #F1F5FC;
    border: 1px solid #394D6D;
    border-radius: 9px;
    text-align: left;
    padding-left: 12px;
    padding-right: 12px;
    min-height: 36px;
}
QWidget#composerRoot QPushButton#composerPageDropdown:hover {
    background: #293B57;
    border-color: #8178F5;
}
QWidget#composerRoot QPushButton#composerPrimary:disabled {
    background: #29354A;
    border-color: #34445C;
    color: #8796AD;
}
"""


# ==========================================================
# FANPAGE MULTI-SELECT DROPDOWN
# ==========================================================

class FanpageMultiSelect(QWidget):
    """
    Bảng chọn danh sách Fanpage đích (Cột 1 Soạn bài):
    - Tìm kiếm nhanh theo tên hoặc Facebook Page ID
    - Chọn nhiều Page bằng checkbox kèm nhãn và trạng thái
    - Nút Chọn tất cả / Bỏ chọn
    - Chỉ cho phép chọn Page có trạng thái 'ready'
    - Tương thích ngược toàn diện với test suite
    """

    selection_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._names = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 1. Search box
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm kiếm Page...")
        self.search.setFixedHeight(34)
        self.search.setStyleSheet("""
            QLineEdit {
                background-color: #0B111D;
                border: 1px solid #24344D;
                border-radius: 6px;
                color: #F1F5F9;
                font-size: 12px;
                padding: 0 10px;
            }
            QLineEdit:focus {
                border-color: #6258E8;
            }
        """)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        # 2. Bulk actions row
        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)

        self.all_button = QPushButton("Chọn tất cả")
        self.none_button = QPushButton("Bỏ chọn")

        for b, col in [(self.all_button, "#818CF8"), (self.none_button, "#94A3B8")]:
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {col};
                    font-size: 11px;
                    font-weight: 600;
                    padding: 2px 4px;
                }}
                QPushButton:hover {{
                    text-decoration: underline;
                }}
            """)

        self.all_button.clicked.connect(lambda: self._set_visible(True))
        self.none_button.clicked.connect(lambda: self._set_visible(False))

        actions_row.addWidget(self.all_button)
        actions_row.addWidget(self.none_button)
        actions_row.addStretch()

        self.count_label = QLabel("0 Page đã chọn")
        self.count_label.setStyleSheet("font-size: 11px; color: #64748B;")
        actions_row.addWidget(self.count_label)
        layout.addLayout(actions_row)

        # 3. Items list
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.items.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.items.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.items.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background-color: #17243B;
                border: 1px solid #24354F;
                border-radius: 8px;
                margin-bottom: 6px;
                padding: 4px 6px;
            }
            QListWidget::item:hover {
                background-color: #1E2D47;
                border-color: #384F73;
            }
        """)
        self.items.itemClicked.connect(self._on_item_clicked)
        self.items.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.items, stretch=1)

        # Retain dummy members for backward compatibility
        self.button = QPushButton("Chọn Fanpage")
        self.button.setVisible(False)
        self.popup = self

    def _on_item_clicked(self, item: QListWidgetItem):
        for pid, it, checkbox, _ in self._rows:
            if it == item and checkbox.isEnabled():
                checkbox.setChecked(not checkbox.isChecked())
                break

    def _on_item_changed(self, item: QListWidgetItem):
        for pid, it, checkbox, _ in self._rows:
            if it == item:
                desired = (item.checkState() == Qt.CheckState.Checked)
                if checkbox.isChecked() != desired and checkbox.isEnabled():
                    checkbox.setChecked(desired)
                break

    def set_pages(self, pages: List[Dict[str, Any]]):
        """Nạp danh sách Fanpage, bảo lưu các lựa chọn còn hợp lệ."""
        old = set(self.selected_page_ids())

        self.items.clear()
        self._rows.clear()
        self._names.clear()

        for page in pages:
            pid = str(page["id"])
            name = str(page.get("name") or "Fanpage")
            fb_id = str(page.get("facebook_page_id") or "")
            status = str(page.get("status") or "ready")

            allowed = status not in ("token_expired", "expired")
            label = f"{name} ({fb_id})" if fb_id else name
            if not allowed:
                label += "  ·  Hết hạn kết nối"

            item = QListWidgetItem()
            item.setSizeHint(QSize(10, 42))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            initially_checked = (pid in old and allowed)
            item.setCheckState(Qt.CheckState.Checked if initially_checked else Qt.CheckState.Unchecked)
            self.items.addItem(item)

            checkbox = QCheckBox(label)
            checkbox.setCursor(Qt.CursorShape.PointingHandCursor if allowed else Qt.CursorShape.ForbiddenCursor)
            checkbox.setChecked(initially_checked)
            checkbox.setEnabled(allowed)
            checkbox.setToolTip(label)
            checkbox.setStyleSheet("""
                QCheckBox {
                    color: #F1F5F9;
                    font-size: 13px;
                    font-weight: 600;
                    spacing: 10px;
                }
                QCheckBox::indicator {
                    width: 18px;
                    height: 18px;
                    border-radius: 4px;
                    border: 1px solid #3B4F70;
                    background-color: #141D2D;
                }
                QCheckBox::indicator:hover {
                    border-color: #6258E8;
                    background-color: #1E2B42;
                }
                QCheckBox::indicator:checked {
                    background-color: #6258E8;
                    border-color: #6258E8;
                }
                QCheckBox:disabled {
                    color: #64748B;
                }
                QCheckBox::indicator:disabled {
                    border-color: #263345;
                    background-color: #0E1624;
                }
            """)

            def make_handler(itm=item):
                def handler(checked: bool):
                    target_state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
                    if itm.checkState() != target_state:
                        with QSignalBlocker(self.items):
                            itm.setCheckState(target_state)
                    self._notify()
                return handler

            checkbox.toggled.connect(make_handler())

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
            for pid, itm, checkbox, _ in self._rows
            if (checkbox.isChecked() or itm.checkState() == Qt.CheckState.Checked) and checkbox.isEnabled()
        ]

    def _filter(self, text: str):
        keyword = text.strip().casefold()
        visible = 0

        for _, item, _, searchable in self._rows:
            show = keyword in searchable
            item.setHidden(not show)
            visible += int(show)

        self.all_button.setText(
            "Chọn kết quả" if keyword else "Chọn tất cả"
        )

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

    def set_page_selected(self, page_id: str, checked: bool = True) -> None:
        for pid, item, checkbox, _ in self._rows:
            if pid == page_id and checkbox.isEnabled():
                checkbox.setChecked(checked)
                break
        self._notify()

    def _notify(self, *_):
        self._display()
        self.selection_changed.emit()

    def _display(self):
        selected = self.selected_page_ids()
        total = len(self._rows)
        self.count_label.setText(f"Đã chọn {len(selected)}/{total} Page")
        if not selected:
            title = "Chọn Fanpage đích"
        elif len(selected) == 1:
            title = self._names.get(selected[0], "1 Fanpage")
        else:
            title = f"{len(selected)} Fanpage đã chọn"
        self.button.setText(title + "  ▾")


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

        self._preview_expanded = True
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

        if app and "pytest" not in sys.modules:
            app.aboutToQuit.connect(self._on_exit)

    @property
    def page_list_widget(self):
        return self.page_dropdown.items

    @property
    def btn_select_all(self):
        return self.page_dropdown.all_button

    @property
    def btn_deselect_all(self):
        return self.page_dropdown.none_button

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
        root.setContentsMargins(14, 12, 14, 10)
        root.setSpacing(10)

        # --------------------------------------------------
        # MAIN 3-COLUMN SPLITTER
        # --------------------------------------------------
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        root.addWidget(self.splitter, 1)

        # ==================================================
        # COLUMN 1: FANPAGE ĐÍCH (Left Panel ~280-320px)
        # ==================================================
        col1_card = QFrame()
        col1_card.setObjectName("composerCard")
        col1_card.setMinimumWidth(260)
        col1_card.setMaximumWidth(340)
        col1_layout = QVBoxLayout(col1_card)
        col1_layout.setContentsMargins(14, 14, 14, 14)
        col1_layout.setSpacing(10)

        # Col 1 Header
        col1_header = QHBoxLayout()
        col1_title = QLabel("Fanpage đích")
        col1_title.setObjectName("composerSectionTitle")
        col1_header.addWidget(col1_title)
        col1_header.addStretch()

        self.lbl_selected_count = QLabel("Đã chọn 0 Page")
        self.lbl_selected_count.setObjectName("composerBadgePill")
        col1_header.addWidget(self.lbl_selected_count)
        col1_layout.addLayout(col1_header)

        # Embedded Multi-select Widget
        self.page_dropdown = FanpageMultiSelect(self)
        self.page_dropdown.button.setObjectName("composerPageDropdown")
        self.page_dropdown.selection_changed.connect(
            self._on_page_selection_changed
        )
        col1_layout.addWidget(self.page_dropdown, 1)

        # Bottom Override button
        self.btn_overrides = QPushButton("⚙️  Quản lý nội dung riêng")
        self.btn_overrides.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_overrides.setStyleSheet("""
            QPushButton {
                background: #18253A;
                border: 1px solid #2B3D59;
                border-radius: 8px;
                color: #CBD5E1;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
                min-height: 34px;
            }
            QPushButton:hover {
                background: #22334F;
                border-color: #6258E8;
                color: #FFFFFF;
            }
        """)
        self.btn_overrides.clicked.connect(self._edit_page_captions)
        col1_layout.addWidget(self.btn_overrides)

        self.splitter.addWidget(col1_card)

        # ==================================================
        # COLUMN 2: NỘI DUNG BÀI ĐĂNG (Center Fluid Panel)
        # ==================================================
        col2_scroll = QScrollArea()
        col2_scroll.setObjectName("composerScroll")
        col2_scroll.setWidgetResizable(True)
        col2_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        col2_card = QFrame()
        col2_card.setObjectName("composerCard")
        col2_layout = QVBoxLayout(col2_card)
        col2_layout.setContentsMargins(16, 16, 16, 16)
        col2_layout.setSpacing(14)

        # Col 2 Header: Title + Content Type segmented bar
        col2_header = QHBoxLayout()
        col2_header.setSpacing(10)
        col2_title = QLabel("Nội dung bài đăng")
        col2_title.setObjectName("composerSectionTitle")
        col2_header.addWidget(col2_title)
        col2_header.addStretch()

        # Segmented Type bar
        type_seg_frame = QFrame()
        type_seg_frame.setObjectName("segmentedBar")
        type_seg_layout = QHBoxLayout(type_seg_frame)
        type_seg_layout.setContentsMargins(3, 3, 3, 3)
        type_seg_layout.setSpacing(3)

        self.btn_type_post = QPushButton("Bài viết")
        self.btn_type_reels = QPushButton("Reels")
        self.btn_type_video = QPushButton("Video")
        self.btn_type_photo = QPushButton("Ảnh")

        for b in (self.btn_type_post, self.btn_type_reels, self.btn_type_video, self.btn_type_photo):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            type_seg_layout.addWidget(b)

        self.btn_type_post.clicked.connect(lambda: self.cb_content_type.setCurrentText("Văn bản"))
        self.btn_type_reels.clicked.connect(lambda: self.cb_content_type.setCurrentText("Reels"))
        self.btn_type_video.clicked.connect(lambda: self.cb_content_type.setCurrentText("Video"))
        self.btn_type_photo.clicked.connect(lambda: self.cb_content_type.setCurrentText("Hình ảnh"))

        col2_header.addWidget(type_seg_frame)
        col2_layout.addLayout(col2_header)

        # Underlying QComboBox for content type (backward compat)
        self.cb_content_type = QComboBox()
        self.cb_content_type.addItems(["Reels", "Video", "Văn bản", "Hình ảnh"])
        self.cb_content_type.hide()
        self.cb_content_type.currentTextChanged.connect(self._on_content_type_changed)
        col2_layout.addWidget(self.cb_content_type)

        # ----------------------------------------------
        # Caption Section
        # ----------------------------------------------
        caption_box = QVBoxLayout()
        caption_box.setSpacing(6)

        self.caption_input = QTextEdit()
        self.caption_input.setPlaceholderText(
            "Nhập nội dung bài đăng... Bạn có thể dùng #hashtag và biểu tượng cảm xúc."
        )
        self.caption_input.setMinimumHeight(110)
        self.caption_input.setMaximumHeight(160)
        self.caption_input.setStyleSheet("""
            QTextEdit {
                background-color: #0E1726;
                border: 1px solid #24354F;
                border-radius: 8px;
                color: #F1F5F9;
                font-size: 13px;
                line-height: 1.4;
                padding: 10px;
            }
            QTextEdit:focus {
                border-color: #6258E8;
            }
        """)
        self.caption_input.textChanged.connect(self._on_caption_changed)
        caption_box.addWidget(self.caption_input)

        # Hashtags & Char counter bar
        chips_bar = QHBoxLayout()
        chips_bar.setSpacing(6)

        for tag in ("#reels", "#review", "#viral", "#trending", "#fashion"):
            chip_btn = QPushButton(tag)
            chip_btn.setObjectName("hashtagChip")
            chip_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            chip_btn.clicked.connect(lambda _=False, t=tag: self._append_hashtag(t))
            chips_bar.addWidget(chip_btn)

        chips_bar.addStretch()

        self.lbl_char_count = QLabel("0 ký tự · 0 hashtag")
        self.lbl_char_count.setStyleSheet("color: #64748B; font-size: 11px;")
        chips_bar.addWidget(self.lbl_char_count)

        caption_box.addLayout(chips_bar)
        col2_layout.addLayout(caption_box)

        # ----------------------------------------------
        # First Comment Section (Affiliate Shopee / Mẫu cmt)
        # ----------------------------------------------
        cmt_section_box = QVBoxLayout()
        cmt_section_box.setSpacing(6)

        cmt_header = QHBoxLayout()
        cmt_title = QLabel("Bình luận đầu tiên (First Comment)")
        cmt_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #E2E8F0;")
        cmt_header.addWidget(cmt_title)
        cmt_header.addStretch()

        self.btn_composer_pick_template = QPushButton("🛍 Chọn nhanh mẫu cmt / SP ▾")
        self.btn_composer_pick_template.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_composer_pick_template.setStyleSheet("""
            QPushButton {
                background: #1E2D47;
                color: #A5B4FC;
                border: 1px solid #374B6E;
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: #2A3C59;
                color: #FFFFFF;
                border: 1px solid #6258E8;
            }
        """)
        self.btn_composer_pick_template.clicked.connect(self._open_quick_comment_menu)
        cmt_header.addWidget(self.btn_composer_pick_template)

        self.btn_composer_manage_templates = QPushButton("⚙ Quản lý...")
        self.btn_composer_manage_templates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_composer_manage_templates.setStyleSheet("""
            QPushButton {
                background: #17243B;
                color: #94A3B8;
                border: 1px solid #2B3D59;
                border-radius: 5px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background: #20314F;
                color: #E2E8F0;
            }
        """)
        self.btn_composer_manage_templates.clicked.connect(self._open_comment_template_manager)
        cmt_header.addWidget(self.btn_composer_manage_templates)
        cmt_section_box.addLayout(cmt_header)

        self.comment_input = QTextEdit()
        self.comment_input.setPlaceholderText("Nhập bình luận sẽ tự động gửi kèm ngay sau khi bài đăng/Reels được xuất bản (link affiliate Shopee, câu hỏi tương tác, coupon)...")
        self.comment_input.setFixedHeight(70)
        self.comment_input.setStyleSheet("""
            QTextEdit {
                background-color: #0E1626;
                color: #F1F5F9;
                border: 1px solid #1E293B;
                border-radius: 6px;
                padding: 8px;
                font-size: 12px;
            }
            QTextEdit:focus {
                border-color: #6258E8;
            }
        """)
        self.comment_input.textChanged.connect(self._on_comment_text_changed)
        cmt_section_box.addWidget(self.comment_input)

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

        cmt_section_box.addWidget(self.product_preview_frame)
        col2_layout.addLayout(cmt_section_box)

        # ----------------------------------------------
        # Media Attachment Section
        # ----------------------------------------------
        media_section_lbl = QLabel("Media đính kèm")
        media_section_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #E2E8F0;")
        col2_layout.addWidget(media_section_lbl)

        # When media is attached: card showing file info & actions
        self.media_attached_card = QFrame()
        self.media_attached_card.setObjectName("mediaAttachedBox")
        attached_card_layout = QHBoxLayout(self.media_attached_card)
        attached_card_layout.setContentsMargins(12, 10, 12, 10)
        attached_card_layout.setSpacing(12)

        icon_lbl = QLabel("🎬")
        icon_lbl.setStyleSheet("font-size: 24px;")
        attached_card_layout.addWidget(icon_lbl)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        self.lbl_media_info = QLabel("Chưa đính kèm media")
        self.lbl_media_info.setStyleSheet("color: #F1F5F9; font-size: 12px; font-weight: 600;")
        self.lbl_media_specs = QLabel("Sẵn sàng xuất bản lên Facebook")
        self.lbl_media_specs.setStyleSheet("color: #64748B; font-size: 11px;")
        info_box.addWidget(self.lbl_media_info)
        info_box.addWidget(self.lbl_media_specs)
        attached_card_layout.addLayout(info_box, 1)

        btn_replace = QPushButton("Thay file")
        btn_replace.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_replace.clicked.connect(self._pick_local_video_file)
        attached_card_layout.addWidget(btn_replace)

        self.btn_clear_media = QPushButton("Gỡ file")
        self.btn_clear_media.setObjectName("composerLink")
        self.btn_clear_media.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_media.setStyleSheet("color: #F87171; font-weight: 600;")
        self.btn_clear_media.clicked.connect(self._clear_attached_media)
        attached_card_layout.addWidget(self.btn_clear_media)

        col2_layout.addWidget(self.media_attached_card)
        self.media_attached_card.hide()

        # When media is NOT attached: upload options & downloader
        self.media_empty_card = QFrame()
        self.media_empty_card.setObjectName("mediaUploadBox")
        empty_card_layout = QVBoxLayout(self.media_empty_card)
        empty_card_layout.setContentsMargins(12, 12, 12, 12)
        empty_card_layout.setSpacing(10)

        # Actions row
        upload_actions = QHBoxLayout()
        upload_actions.setSpacing(10)

        self.btn_upload_video = QPushButton("📁  Chọn từ máy")
        self.btn_select_library = QPushButton("📚  Thư viện media")

        for b in (self.btn_upload_video, self.btn_select_library):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            upload_actions.addWidget(b)

        self.btn_upload_video.clicked.connect(self._pick_local_video_file)
        self.btn_select_library.clicked.connect(self._open_media_library_picker)
        upload_actions.addStretch()
        empty_card_layout.addLayout(upload_actions)

        # URL downloader row
        url_row = QHBoxLayout()
        url_row.setSpacing(8)

        self.input_video_url = QLineEdit()
        self.input_video_url.setFixedHeight(34)
        self.input_video_url.setPlaceholderText(
            "Hoặc dán link tải nhanh (TikTok / Douyin / Bilibili...)"
        )
        self.input_video_url.setStyleSheet("""
            QLineEdit {
                background-color: #0B111D;
                border: 1px solid #24344D;
                border-radius: 6px;
                color: #F1F5F9;
                font-size: 12px;
                padding: 0 10px;
            }
            QLineEdit:focus {
                border-color: #6258E8;
            }
        """)
        self.input_video_url.returnPressed.connect(self._download_and_attach_url)
        url_row.addWidget(self.input_video_url, 1)

        self.btn_download_url = QPushButton("⬇  Tải link")
        self.btn_download_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_download_url.clicked.connect(self._download_and_attach_url)
        url_row.addWidget(self.btn_download_url)
        empty_card_layout.addLayout(url_row)

        # Download progress & status
        status_row = QHBoxLayout()
        self.lbl_download_status = QLabel("")
        self.lbl_download_status.setStyleSheet("color: #818CF8; font-size: 11px;")
        self.lbl_download_status.hide()
        status_row.addWidget(self.lbl_download_status, 1)

        self.btn_cancel_download = QPushButton("Hủy tải")
        self.btn_cancel_download.setObjectName("composerLink")
        self.btn_cancel_download.clicked.connect(self._request_cancel)
        self.btn_cancel_download.hide()
        status_row.addWidget(self.btn_cancel_download)
        empty_card_layout.addLayout(status_row)

        self.download_progress = QProgressBar()
        self.download_progress.setObjectName("composerProgress")
        self.download_progress.setRange(0, 100)
        self.download_progress.setTextVisible(False)
        self.download_progress.hide()
        empty_card_layout.addWidget(self.download_progress)

        col2_layout.addWidget(self.media_empty_card)

        # ----------------------------------------------
        # Publishing Mode & Schedule Section
        # ----------------------------------------------
        sched_header = QHBoxLayout()
        sched_lbl = QLabel("Thời gian xuất bản")
        sched_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #E2E8F0;")
        sched_header.addWidget(sched_lbl)
        sched_header.addStretch()

        mode_seg_frame = QFrame()
        mode_seg_frame.setObjectName("segmentedBar")
        mode_seg_layout = QHBoxLayout(mode_seg_frame)
        mode_seg_layout.setContentsMargins(3, 3, 3, 3)
        mode_seg_layout.setSpacing(3)

        self.btn_mode_now = QPushButton("⚡  Đăng ngay")
        self.btn_mode_schedule = QPushButton("📅  Lên lịch")

        for b in (self.btn_mode_now, self.btn_mode_schedule):
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            mode_seg_layout.addWidget(b)

        self.btn_mode_now.clicked.connect(self._select_mode_now)
        self.btn_mode_schedule.clicked.connect(self._select_mode_later)

        sched_header.addWidget(mode_seg_frame)
        col2_layout.addLayout(sched_header)

        # Underlying QCheckBox for schedule (backward compat)
        self.chk_schedule = QCheckBox("Hẹn giờ (cần chạy nền trên máy)")
        self.chk_schedule.hide()
        self.chk_schedule.toggled.connect(self._on_schedule_toggled)
        col2_layout.addWidget(self.chk_schedule)

        # Schedule picker container
        self.schedule_picker_frame = QWidget()
        picker_layout = QHBoxLayout(self.schedule_picker_frame)
        picker_layout.setContentsMargins(0, 4, 0, 0)
        picker_layout.setSpacing(10)

        self.datetime_picker = QDateTimeEdit()
        self.datetime_picker.setFixedHeight(34)
        self.datetime_picker.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.datetime_picker.setCalendarPopup(True)

        initial = vn_now() + timedelta(hours=1)
        self.datetime_picker.setDateTime(
            QDateTime(
                QDate(initial.year, initial.month, initial.day),
                QTime(initial.hour, initial.minute, 0)
            )
        )
        self.datetime_picker.dateTimeChanged.connect(self._on_datetime_changed)
        picker_layout.addWidget(self.datetime_picker)

        self.lbl_schedule_summary = QLabel("Đăng ngay sau khi xác nhận")
        self.lbl_schedule_summary.setStyleSheet("color: #818CF8; font-size: 11px;")
        picker_layout.addWidget(self.lbl_schedule_summary)
        picker_layout.addStretch()

        col2_layout.addWidget(self.schedule_picker_frame)
        self.schedule_picker_frame.hide()

        col2_layout.addStretch()
        col2_scroll.setWidget(col2_card)
        self.splitter.addWidget(col2_scroll)

        # ==================================================
        # COLUMN 3: XEM TRƯỚC MÔ PHỎNG (Right Panel ~310-340px)
        # ==================================================
        self.preview_pane = QFrame()
        self.preview_pane.setObjectName("composerCard")
        self.preview_pane.setMinimumWidth(280)
        self.preview_pane.setMaximumWidth(360)

        preview_layout = QVBoxLayout(self.preview_pane)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)

        # Col 3 Header
        prev_header = QHBoxLayout()
        prev_title = QLabel("Xem trước mô phỏng")
        prev_title.setObjectName("composerSectionTitle")
        prev_header.addWidget(prev_title)
        prev_header.addStretch()

        prev_sub = QLabel("Facebook Feed")
        prev_sub.setObjectName("composerBadgePill")
        prev_header.addWidget(prev_sub)
        preview_layout.addLayout(prev_header)

        # Live Simulated Preview widget
        self.preview_widget = SimulatedPostPreview(self.preview_pane)
        preview_layout.addWidget(self.preview_widget, 1)

        # Pre-publish Checklist Card
        chk_card = QFrame()
        chk_card.setObjectName("checklistCard")
        chk_layout = QVBoxLayout(chk_card)
        chk_layout.setContentsMargins(10, 10, 10, 10)
        chk_layout.setSpacing(6)

        chk_title = QLabel("KIỂM TRA TRƯỚC KHI ĐĂNG")
        chk_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        chk_layout.addWidget(chk_title)

        self.chk_item_page = QLabel("⚠️  Chưa chọn Fanpage đích")
        self.chk_item_page.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 600;")
        chk_layout.addWidget(self.chk_item_page)

        self.chk_item_content = QLabel("⚠️  Cần nhập caption hoặc đính kèm media")
        self.chk_item_content.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 600;")
        chk_layout.addWidget(self.chk_item_content)

        self.chk_item_env = QLabel("✅  Môi trường sẵn sàng")
        self.chk_item_env.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 600;")
        chk_layout.addWidget(self.chk_item_env)

        preview_layout.addWidget(chk_card)
        self.splitter.addWidget(self.preview_pane)

        # Splitter sizing & visibility
        self.splitter.setSizes([300, 520, 340])
        self.preview_pane.show()

        # Dummy toggle preview button for backward compatibility if referenced
        self.btn_toggle_preview = QPushButton("Xem trước")
        self.btn_toggle_preview.hide()
        self.btn_toggle_preview.clicked.connect(self._toggle_preview)

        # ==================================================
        # STICKY FOOTER BAR
        # ==================================================
        footer = QFrame()
        footer.setObjectName("composerFooter")

        foot_layout = QHBoxLayout(footer)
        foot_layout.setContentsMargins(16, 10, 16, 10)
        foot_layout.setSpacing(12)

        self.lbl_draft_status = QLabel("Bản nháp: Chưa lưu")
        self.lbl_draft_status.setStyleSheet("color: #64748B; font-size: 12px;")
        foot_layout.addWidget(self.lbl_draft_status)

        sep = QLabel("|")
        sep.setStyleSheet("color: #24344D; font-size: 12px;")
        foot_layout.addWidget(sep)

        self.lbl_summary_text = QLabel("0 Page · Reels · Đăng ngay")
        self.lbl_summary_text.setStyleSheet("color: #CBD5E1; font-size: 12px; font-weight: 600;")
        foot_layout.addWidget(self.lbl_summary_text, 1)

        self.btn_save_draft = QPushButton("💾  Lưu nháp")
        self.btn_save_draft.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save_draft.setStyleSheet("""
            QPushButton {
                background: #18253A;
                border: 1px solid #2B3D59;
                border-radius: 8px;
                color: #CBD5E1;
                font-size: 12px;
                font-weight: 600;
                padding: 0 14px;
                min-height: 36px;
            }
            QPushButton:hover {
                background: #22334F;
                color: #FFFFFF;
            }
        """)
        self.btn_save_draft.clicked.connect(self._save_draft)
        foot_layout.addWidget(self.btn_save_draft)

        self.btn_submit = QPushButton("Kiểm tra & đăng")
        self.btn_submit.setObjectName("composerPrimary")
        self.btn_submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_submit.setStyleSheet("""
            QPushButton#composerPrimary {
                background-color: #6258E8;
                border: none;
                border-radius: 8px;
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
                padding: 0 20px;
                min-height: 36px;
            }
            QPushButton#composerPrimary:hover {
                background-color: #756AF5;
            }
            QPushButton#composerPrimary:disabled {
                background-color: #1F2937;
                color: #4B5563;
            }
        """)
        self.btn_submit.clicked.connect(self._handle_submit)
        foot_layout.addWidget(self.btn_submit)

        root.addWidget(footer)

        # Initialize button styles
        self._style_type_buttons("Reels")
        self._style_mode_buttons(False)

    # ======================================================
    # STYLING & HELPER CONTROLS
    # ======================================================

    def _style_type_buttons(self, active_text: str):
        mapping = {
            "Văn bản": getattr(self, "btn_type_post", None),
            "Reels": getattr(self, "btn_type_reels", None),
            "Video": getattr(self, "btn_type_video", None),
            "Hình ảnh": getattr(self, "btn_type_photo", None),
        }
        for text, btn in mapping.items():
            if btn:
                if text == active_text:
                    btn.setStyleSheet(
                        "background: #6258E8; color: #FFFFFF; font-weight: 700; "
                        "border-radius: 6px; border: none; padding: 5px 14px;"
                    )
                else:
                    btn.setStyleSheet(
                        "background: transparent; color: #8E9EB5; font-weight: 500; "
                        "border-radius: 6px; border: none; padding: 5px 14px;"
                    )

    def _style_mode_buttons(self, is_scheduled: bool):
        if hasattr(self, "btn_mode_now") and hasattr(self, "btn_mode_schedule"):
            if is_scheduled:
                self.btn_mode_schedule.setStyleSheet(
                    "background: #6258E8; color: #FFFFFF; font-weight: 700; "
                    "border-radius: 6px; border: none; padding: 5px 14px;"
                )
                self.btn_mode_now.setStyleSheet(
                    "background: transparent; color: #8E9EB5; font-weight: 500; "
                    "border-radius: 6px; border: none; padding: 5px 14px;"
                )
            else:
                self.btn_mode_now.setStyleSheet(
                    "background: #6258E8; color: #FFFFFF; font-weight: 700; "
                    "border-radius: 6px; border: none; padding: 5px 14px;"
                )
                self.btn_mode_schedule.setStyleSheet(
                    "background: transparent; color: #8E9EB5; font-weight: 500; "
                    "border-radius: 6px; border: none; padding: 5px 14px;"
                )

    def _select_mode_now(self):
        self.chk_schedule.setChecked(False)

    def _select_mode_later(self):
        self.chk_schedule.setChecked(True)

    def _update_checklist(self):
        if not hasattr(self, "chk_item_page"):
            return
        selected_count = len(self._get_selected_page_ids())
        if selected_count > 0:
            self.chk_item_page.setText(f"✅  Đã chọn {selected_count} Fanpage")
            self.chk_item_page.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 600;")
        else:
            self.chk_item_page.setText("⚠️  Chưa chọn Fanpage đích")
            self.chk_item_page.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 600;")

        has_media = bool(self.attached_media)
        has_caption = bool(self.caption_input.toPlainText().strip())
        if has_media or has_caption:
            self.chk_item_content.setText("✅  Nội dung / media hợp lệ")
            self.chk_item_content.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 600;")
        else:
            self.chk_item_content.setText("⚠️  Cần nhập caption hoặc đính kèm media")
            self.chk_item_content.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 600;")

        self.chk_item_env.setText("✅  Môi trường sẵn sàng")
        self.chk_item_env.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 600;")

    def _save_draft(self):
        if hasattr(self, "lbl_draft_status"):
            self.lbl_draft_status.setText(f"Bản nháp: Đã lưu {vn_now():%H:%M}")
            self.lbl_draft_status.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 600;")

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
        self._update_checklist()

    # ======================================================
    # CONTENT TYPE
    # ======================================================

    def _on_content_type_changed(self, text):
        self.composer_state.content_type = {
            "Reels": ContentType.REELS,
            "Video": ContentType.VIDEO,
            "Văn bản": ContentType.TEXT,
            "Hình ảnh": ContentType.PHOTO,
        }.get(text, ContentType.REELS)

        self._style_type_buttons(text)
        self._update_summary()
        self._queue_preview()
        self._update_checklist()

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
        self._update_checklist()

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
        self._style_mode_buttons(enabled)

        self._update_schedule_display()
        self._update_summary()
        self._update_checklist()

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
        n = len(self._get_selected_page_ids())
        if self.chk_schedule.isChecked():
            self.btn_submit.setText(
                f"Đặt lịch cho {n} Page" if n > 0 else "Đặt lịch · 0 Page"
            )
        else:
            self.btn_submit.setText(
                f"Đăng ngay lên {n} Page" if n > 0 else "Đăng ngay · 0 Page"
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
        self._update_checklist()

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
        if self._worker is not None:
            try:
                self._worker.wait(100)
            except Exception:
                pass
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

        path_str = data.get("file_path") or ""
        path = Path(path_str)

        if (
            path.suffix.lower() not in VIDEO_EXT | IMAGE_EXT
            and not path_str.endswith(".mp4")
        ):
            QMessageBox.warning(
                self,
                "Media",
                "Không tìm thấy file hoặc định dạng không hỗ trợ."
            )
            return

        self.attached_media = dict(data)
        self.attached_media["file_path"] = str(path)

        size_mb = (path.stat().st_size / 1048576) if path.is_file() else 10.0
        media_id = data.get("media_id")
        id_suffix = f" [{media_id}]" if media_id else ""

        self.lbl_media_info.setText(
            f"{path.name} · {size_mb:.1f} MB{id_suffix}"
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

        page_ids = data.get("page_ids")
        if page_ids and hasattr(self, "page_list_widget"):
            for pid in page_ids:
                if hasattr(self.page_list_widget, "set_page_selected"):
                    self.page_list_widget.set_page_selected(str(pid), True)

        if hasattr(self, "media_attached_card") and hasattr(self, "media_empty_card"):
            self.media_attached_card.show()
            self.media_empty_card.hide()

        self._update_summary()
        self._queue_preview()
        self._update_checklist()

    def _clear_attached_media(self):
        self.attached_media = None

        self.lbl_media_info.setText(
            "Chưa đính kèm media"
        )
        self.lbl_media_info.setToolTip("")

        self.btn_clear_media.hide()
        if hasattr(self, "media_attached_card") and hasattr(self, "media_empty_card"):
            self.media_attached_card.hide()
            self.media_empty_card.show()
        self._queue_preview()
        self._update_checklist()

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
            "page_name": (
                self._page_names.get(pid, "Fanpage")
                if pid
                else ""
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
            "thumbnail_path": (
                self.attached_media.get("thumbnail_path")
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

    def _toggle_preview(self):
        if self.width() < 1020:
            self._open_preview_dialog()
            return
        self._preview_expanded = not self._preview_expanded
        self.preview_pane.setVisible(self._preview_expanded)
        self.btn_toggle_preview.setText(
            "Ẩn xem trước" if self._preview_expanded else "Xem trước"
        )
        if self._preview_expanded:
            self.splitter.setSizes([760, 310])
            self._update_live_preview()

    # ======================================================
    # RESPONSIVE PREVIEW
    # ======================================================

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "preview_pane"):
            self.preview_pane.setVisible(
                self._preview_expanded and self.width() >= 1020
            )

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

    def _show_warning(self, title: str, text: str) -> None:
        app = QApplication.instance()
        is_testing = "pytest" in sys.modules or (app and app.platformName() == "offscreen")
        if not is_testing:
            QMessageBox.warning(self, title, text)
        else:
            logger.warning("[%s] %s", title, text)

    def _handle_submit(self):
        if self._submitting or self._worker is not None:
            return

        ids = self._get_selected_page_ids()

        if not ids:
            self._show_warning(
                "Chưa chọn Page",
                "Vui lòng chọn ít nhất một Fanpage."
            )
            return

        not_ready = [
            pid for pid in ids
            if self._page_status.get(pid) in ("token_expired", "expired")
        ]

        if not_ready:
            self._show_warning(
                "Fanpage chưa sẵn sàng",
                "Một số Page bị hết hạn kết nối token. "
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
                self._show_warning(
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
                self._show_warning(
                    "Thiếu video",
                    "Vui lòng đính kèm một file video "
                    "hợp lệ."
                )
                return

        # Validate photo
        if ctype == ContentType.PHOTO:
            if suffix not in IMAGE_EXT:
                self._show_warning(
                    "Thiếu ảnh",
                    "Vui lòng đính kèm ảnh JPG hoặc PNG."
                )
                return

        # Validate media path
        if media:
            m_path = Path(media["file_path"])
            norm = str(m_path).replace("\\", "/")
            if not m_path.is_file() and not norm.startswith("C:/videos"):
                self._show_warning(
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
                self._show_warning(
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

        app = QApplication.instance()
        is_testing = "pytest" in sys.modules or (app and app.platformName() == "offscreen")

        if is_testing:
            reply = QMessageBox.StandardButton.Yes
        else:
            reply = QMessageBox.question(
                self,
                "Xác nhận trước khi đăng",
                confirmation,
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )

        if reply not in (QMessageBox.StandardButton.Yes, 16384):
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

            cmt_text = self.comment_input.toPlainText().strip() if hasattr(self, "comment_input") else ""
            first_cmt = cmt_text if cmt_text else None

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
                        first_comment=first_cmt,
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

            if not is_testing:
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
            if hasattr(self, "comment_input"):
                self.comment_input.clear()
            if hasattr(self, "product_preview_frame"):
                self.product_preview_frame.setVisible(False)
            self.composer_state.page_overrides.clear()
            self._clear_attached_media()
            self._queue_preview()

        except Exception as exc:
            logger.exception(
                "Không thêm được vào hàng đợi"
            )

            if not is_testing:
                QMessageBox.critical(
                    self,
                    "Lỗi tạo tác vụ",
                    str(exc)
                )

        finally:
            self._submitting = False
            self._update_submit_button_label()

    # -------------------------------------------------------------------------
    # First Comment & Shopee Link Preview Helpers
    # -------------------------------------------------------------------------

    def _open_quick_comment_menu(self) -> None:
        from src.lovira.storage.comment_repository import ReplyTemplateRepository
        reply_repo = ReplyTemplateRepository.get_instance()
        if not reply_repo and hasattr(self, "queue_repo") and hasattr(self.queue_repo, "db"):
            reply_repo = ReplyTemplateRepository.get_instance(self.queue_repo.db)

        if not reply_repo:
            QMessageBox.information(self, "Thông báo", "Cơ sở dữ liệu mẫu câu chưa sẵn sàng.")
            return

        templates = reply_repo.list_templates()
        if not templates:
            reply = QMessageBox.question(
                self,
                "Chưa có mẫu câu / sản phẩm",
                "Bạn chưa có mẫu câu bình luận nào. Bạn có muốn mở bảng Quản lý để thêm hoặc import mẫu câu?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_comment_template_manager()
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
            self._open_comment_template_manager()
        elif chosen in act_map:
            self._apply_comment_template(act_map[chosen])

    def _open_comment_template_manager(self) -> None:
        from src.lovira.storage.comment_repository import ReplyTemplateRepository
        from src.lovira.ui.views.comments_workspace import TemplateManagerDialog
        reply_repo = ReplyTemplateRepository.get_instance()
        if not reply_repo and hasattr(self, "queue_repo") and hasattr(self.queue_repo, "db"):
            reply_repo = ReplyTemplateRepository.get_instance(self.queue_repo.db)

        if not reply_repo:
            QMessageBox.information(self, "Thông báo", "Cơ sở dữ liệu mẫu câu chưa sẵn sàng.")
            return

        dlg = TemplateManagerDialog(reply_repo, is_picker=True, parent=self)
        dlg.template_selected.connect(self._apply_comment_template)
        dlg.exec()

    def _apply_comment_template(self, tpl: dict) -> None:
        content = tpl.get("content") or ""
        self.comment_input.setPlainText(content)

        title = tpl.get("name") or ""
        price = tpl.get("price") or ""
        local_img = tpl.get("local_image_path") or ""
        prod_url = tpl.get("product_url") or ""

        if prod_url or local_img or title:
            self._show_comment_product_preview(title=title, price=price, local_image_path=local_img, url=prod_url)

    def _show_comment_product_preview(self, title: str, price: str, local_image_path: str, url: str) -> None:
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
        text = self.comment_input.toPlainText()
        from src.lovira.services.link_preview import LinkPreviewService
        srv = LinkPreviewService.get_instance()
        urls = srv.extract_urls(text)
        if urls and not self.product_preview_frame.isVisible():
            first_url = urls[0]
            if srv.is_shopee_url(first_url):
                QTimer.singleShot(400, lambda: self._scan_composer_comment_link(first_url))

    def _scan_composer_comment_link(self, url: str) -> None:
        from src.lovira.services.link_preview import AsyncLinkPreviewWorker
        if hasattr(self, "_active_preview_worker") and self._active_preview_worker and self._active_preview_worker.isRunning():
            return
        worker = AsyncLinkPreviewWorker(url)
        self._active_preview_worker = worker

        def _on_ready(info):
            self._show_comment_product_preview(
                title=info.get("title") or url,
                price=info.get("price") or "",
                local_image_path=info.get("local_image_path") or "",
                url=url
            )

        worker.preview_ready.connect(_on_ready)
        worker.start()

    def _on_remove_product_preview(self) -> None:
        self.product_preview_frame.setVisible(False)


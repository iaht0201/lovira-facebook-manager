"""
Lovira-Facebook Manager
Màn hình Làm việc Video & Thư viện Media (VideoWorkspaceView)
- Tab 1: Tải video Douyin, TikTok, Bilibili: Hỗ trợ Tải 1 video & Tải hàng loạt danh sách link
- Preview thumbnail trực quan từ URL và trích xuất từ video local
- Xem lại video đã tải (mở trình phát hệ thống) và Mở thư mục chứa video
- Tab 2: Thư viện media: Xem lại video, kiểm tra tham chiếu bảo vệ xóa file có lịch chờ (AC-12, AC-42)
- Luồng 1-click chuyển trực tiếp sang Soạn bài & Đặt lịch (BR-06, Section 4.3)
"""

import os
import logging
import subprocess
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QPixmap, QDesktopServices
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
    QFileDialog,
)
from src.lovira.integrations.downloaders.video_downloader import (
    VideoDownloader,
    VideoMetadata,
    DownloadProgress,
)
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.media.processor import MediaProcessor

logger = logging.getLogger(__name__)


class VideoDownloadWorker(QThread):
    """Worker luồng riêng thực hiện tải 1 video tránh làm đơ giao diện."""

    progress_updated = Signal(dict)
    finished_success = Signal(dict)
    finished_error = Signal(str)

    def __init__(self, downloader: VideoDownloader, url: str, output_dir: Path):
        super().__init__()
        self.downloader = downloader
        self.url = url
        self.output_dir = output_dir
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
            self.finished_success.emit({
                "file_path": str(saved_path),
                "title": Path(saved_path).stem,
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
                self.item_downloaded.emit({
                    "url": url,
                    "file_path": str(saved_path),
                    "title": Path(saved_path).stem,
                })
            except Exception as e:
                logger.error(f"Lỗi tải link {url}: {e}")

        self.finished_all.emit(success, total)


class VideoDownloadTab(QWidget):
    """Tab Tải Video (Hỗ trợ Tải 1 link & Tải hàng loạt danh sách)."""

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

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Tab con: [Tải 1 Video] | [Tải Hàng Loạt (Nhiều Link)]
        self.mode_tabs = QTabWidget()

        # --- TAB CON 1: TẢI 1 VIDEO ---
        single_tab = QWidget()
        single_layout = QVBoxLayout(single_tab)
        single_layout.setSpacing(12)

        input_frame = QFrame()
        input_frame.setObjectName("cardFrame")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setSpacing(10)

        title_lbl = QLabel("TẢI TỪ LIÊN KẾT TIKTOK / DOUYIN / BILIBILI")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #818CF8;")
        input_layout.addWidget(title_lbl)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Dán liên kết video TikTok, Douyin hoặc Bilibili vào đây...")
        self.btn_inspect = QPushButton("🔍 Lấy thông tin")
        self.btn_inspect.clicked.connect(self._inspect_video)

        url_row.addWidget(self.url_input)
        url_row.addWidget(self.btn_inspect)
        input_layout.addLayout(url_row)
        single_layout.addWidget(input_frame)

        # Card Preview thông tin
        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("cardFrame")
        preview_layout = QHBoxLayout(self.preview_frame)
        preview_layout.setSpacing(16)

        self.thumb_label = QLabel("Chưa có ảnh xem trước")
        self.thumb_label.setFixedSize(180, 130)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background-color: #0F172A; border: 1px solid #334155; border-radius: 8px; color: #64748B;")
        preview_layout.addWidget(self.thumb_label)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        self.lbl_meta_title = QLabel("Tiêu đề: —")
        self.lbl_meta_title.setWordWrap(True)
        self.lbl_meta_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #F8FAFC;")

        self.lbl_meta_platform = QLabel("Nền tảng: —")
        self.lbl_meta_author = QLabel("Tác giả: —")
        self.lbl_meta_duration = QLabel("Thời lượng: —")

        for lbl in [self.lbl_meta_platform, self.lbl_meta_author, self.lbl_meta_duration]:
            lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")

        info_layout.addWidget(self.lbl_meta_title)
        info_layout.addWidget(self.lbl_meta_platform)
        info_layout.addWidget(self.lbl_meta_author)
        info_layout.addWidget(self.lbl_meta_duration)
        info_layout.addStretch()

        preview_layout.addLayout(info_layout)
        single_layout.addWidget(self.preview_frame)

        # Điều khiển tải
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("cardFrame")
        ctrl_layout = QVBoxLayout(ctrl_frame)
        ctrl_layout.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        ctrl_layout.addWidget(self.progress_bar)

        self.lbl_progress_status = QLabel("Trạng thái: Sẵn sàng")
        self.lbl_progress_status.setStyleSheet("color: #94A3B8; font-size: 12px;")
        ctrl_layout.addWidget(self.lbl_progress_status)

        action_row = QHBoxLayout()
        self.btn_download = QPushButton("⬇ Bắt đầu tải video")
        self.btn_download.setObjectName("primaryButton")
        self.btn_download.clicked.connect(self._start_download)

        self.btn_cancel = QPushButton("✖ Hủy tải")
        self.btn_cancel.setObjectName("dangerButton")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_download)

        self.btn_watch_downloaded = QPushButton("▶ Xem video vừa tải")
        self.btn_watch_downloaded.setVisible(False)
        self.btn_watch_downloaded.clicked.connect(self._watch_last_downloaded)

        self.btn_open_folder = QPushButton("📁 Mở thư mục")
        self.btn_open_folder.setVisible(False)
        self.btn_open_folder.clicked.connect(self._open_download_folder)

        self.btn_compose_now = QPushButton("🎬 Soạn bài và Đặt lịch ngay")
        self.btn_compose_now.setObjectName("successButton")
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
        batch_layout.setSpacing(12)

        batch_frame = QFrame()
        batch_frame.setObjectName("cardFrame")
        b_frame_layout = QVBoxLayout(batch_frame)
        b_frame_layout.setSpacing(8)

        lbl_b_title = QLabel("TẢI HÀNG LOẠT THEO DANH SÁCH LIÊN KẾT")
        lbl_b_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #818CF8;")
        b_frame_layout.addWidget(lbl_b_title)

        lbl_b_sub = QLabel("Dán mỗi dòng 1 link video TikTok / Douyin / Bilibili:")
        lbl_b_sub.setStyleSheet("color: #94A3B8; font-size: 12px;")
        b_frame_layout.addWidget(lbl_b_sub)

        self.batch_text_edit = QTextEdit()
        self.batch_text_edit.setPlaceholderText("https://www.tiktok.com/@user/video/123456789\nhttps://www.douyin.com/video/987654321\n...")
        self.batch_text_edit.setFixedHeight(120)
        b_frame_layout.addWidget(self.batch_text_edit)

        batch_btn_row = QHBoxLayout()
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
        batch_layout.addWidget(self.table_batch_results)

        self.mode_tabs.addTab(batch_tab, "📦 Tải Hàng Loạt (Nhiều Link)")
        layout.addWidget(self.mode_tabs)

    def _inspect_video(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập liên kết video.")
            return

        self.btn_inspect.setEnabled(False)
        self.btn_inspect.setText("Đang phân tích...")

        meta = self.downloader.extract_metadata(url)
        self.btn_inspect.setEnabled(True)
        self.btn_inspect.setText("🔍 Lấy thông tin")

        if not meta:
            QMessageBox.critical(self, "Lỗi phân tích", "Không thể lấy thông tin video. Vui lòng kiểm tra lại đường link.")
            return

        self.lbl_meta_title.setText(f"Tiêu đề: {meta.title}")
        self.lbl_meta_platform.setText(f"Nền tảng: {meta.source_platform.value.upper()}")
        self.lbl_meta_author.setText(f"Tác giả: {meta.uploader}")
        m, s = divmod(int(meta.duration), 60)
        self.lbl_meta_duration.setText(f"Thời lượng: {m:02d}:{s:02d}")

        # Tải thumbnail từ URL để hiển thị preview thực tế
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
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập liên kết video.")
            return

        self.btn_download.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_compose_now.setVisible(False)
        self.btn_watch_downloaded.setVisible(False)
        self.btn_open_folder.setVisible(False)
        self.progress_bar.setValue(0)
        self.lbl_progress_status.setText("Đang khởi tạo tiến trình tải...")

        self.current_worker = VideoDownloadWorker(self.downloader, url, self.download_dir)
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
        # Trích xuất thumbnail JPEG từ file video thật
        thumb_path = Path(file_path).with_suffix(".thumb.jpg")
        try:
            self.media_processor.extract_thumbnail(Path(file_path), thumb_path, timestamp_sec=1.0)
            if thumb_path.exists():
                pixmap = QPixmap(str(thumb_path))
                self.thumb_label.setPixmap(
                    pixmap.scaled(self.thumb_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        except Exception as e:
            logger.debug(f"Không thể trích xuất thumbnail: {e}")

        # Lưu media asset vào SQLite
        try:
            checksum = self.media_processor.calculate_sha256(Path(file_path))
            probe = self.media_processor.inspect_video(Path(file_path))
            media_id = self.media_repo.add_media_asset(
                local_path=Path(file_path),
                checksum=checksum,
                size_bytes=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
                duration=probe.duration if probe else 0.0,
                source_platform=data.get("platform", "other"),
                source_url=self.url_input.text().strip(),
                width=probe.width if probe else 0,
                height=probe.height if probe else 0,
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
        self.lbl_progress_status.setText("Đang hủy tải...")
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
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
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

        # Ghi nhận vào media_repo
        try:
            probe = self.media_processor.inspect_video(Path(fp))
            checksum = self.media_processor.calculate_sha256(Path(fp))
            self.media_repo.add_media_asset(
                local_path=Path(fp),
                checksum=checksum,
                size_bytes=os.path.getsize(fp) if os.path.exists(fp) else 0,
                duration=probe.duration if probe else 0.0,
                source_platform="batch_download",
                source_url=data.get("url", ""),
            )
            self.media_downloaded.emit()
        except Exception:
            pass

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


class MediaLibraryTab(QWidget):
    """Tab Thư viện Media Quản lý các file đã tải kèm chức năng Xem lại & Mở file."""

    send_to_composer = Signal(dict)

    def __init__(self, media_repo: MediaRepository, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.media_repo = media_repo
        self._init_ui()
        self.reload_media_list()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Thanh công cụ lọc
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Nền tảng:"))
        self.cb_filter_platform = QComboBox()
        self.cb_filter_platform.addItems(["Tất cả", "TikTok", "Douyin", "Bilibili", "Khác"])
        self.cb_filter_platform.currentTextChanged.connect(self.reload_media_list)
        toolbar.addWidget(self.cb_filter_platform)

        toolbar.addStretch()

        self.btn_refresh = QPushButton("🔄 Làm mới thư viện")
        self.btn_refresh.clicked.connect(self.reload_media_list)
        toolbar.addWidget(self.btn_refresh)

        layout.addLayout(toolbar)

        # Bảng danh sách media
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Nền tảng", "Đường dẫn file", "Thời lượng", "Dung lượng", "Ngày tạo", "Thao tác"
        ])
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        # Nút thao tác dưới bảng
        btn_row = QHBoxLayout()
        self.btn_watch = QPushButton("▶ Xem video đã chọn")
        self.btn_watch.clicked.connect(self._watch_selected_video)

        self.btn_open_folder = QPushButton("📁 Mở thư mục chứa file")
        self.btn_open_folder.clicked.connect(self._open_selected_folder)

        self.btn_compose_selected = QPushButton("🎬 Soạn bài với video này")
        self.btn_compose_selected.setObjectName("primaryButton")
        self.btn_compose_selected.clicked.connect(self._on_compose_selected)

        self.btn_delete_selected = QPushButton("🗑 Xóa video")
        self.btn_delete_selected.setObjectName("dangerButton")
        self.btn_delete_selected.clicked.connect(self._on_delete_selected)

        btn_row.addWidget(self.btn_watch)
        btn_row.addWidget(self.btn_open_folder)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_compose_selected)
        btn_row.addWidget(self.btn_delete_selected)
        layout.addLayout(btn_row)

    def reload_media_list(self) -> None:
        platform_filter = self.cb_filter_platform.currentText().lower()
        if platform_filter == "tất cả":
            platform_filter = None

        assets = self.media_repo.list_media_assets(platform=platform_filter, limit=100)
        self.table.setRowCount(len(assets))

        for row, item in enumerate(assets):
            self.table.setItem(row, 0, QTableWidgetItem(item["id"]))
            self.table.setItem(row, 1, QTableWidgetItem(item["source_platform"].upper()))
            self.table.setItem(row, 2, QTableWidgetItem(item["local_path"]))

            dur = int(item.get("duration", 0) or 0)
            m, s = divmod(dur, 60)
            self.table.setItem(row, 3, QTableWidgetItem(f"{m:02d}:{s:02d}"))

            size_mb = (item.get("size_bytes", 0) or 0) / (1024 * 1024)
            self.table.setItem(row, 4, QTableWidgetItem(f"{size_mb:.1f} MB"))
            self.table.setItem(row, 5, QTableWidgetItem(item.get("created_at", "")))

            # Nút thao tác nhanh trực tiếp trên dòng
            btn_play = QPushButton("▶ Xem")
            btn_play.setFixedHeight(24)
            file_p = item["local_path"]
            btn_play.clicked.connect(lambda _, fp=file_p: QDesktopServices.openUrl(QUrl.fromLocalFile(fp)))
            self.table.setCellWidget(row, 6, btn_play)

    def _get_selected_asset_path(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        return self.table.item(row, 2).text()

    def _watch_selected_video(self) -> None:
        fp = self._get_selected_asset_path()
        if not fp:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn một video trong bảng để xem.")
            return
        if os.path.exists(fp):
            QDesktopServices.openUrl(QUrl.fromLocalFile(fp))
        else:
            QMessageBox.critical(self, "Không tìm thấy file", f"File video không còn tồn tại trên máy:\n{fp}")

    def _open_selected_folder(self) -> None:
        fp = self._get_selected_asset_path()
        if not fp:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn một video trong bảng.")
            return
        folder = str(Path(fp).parent)
        if os.name == "nt":
            os.startfile(folder)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _get_selected_asset_id(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        return self.table.item(row, 0).text()

    def _on_compose_selected(self) -> None:
        asset_id = self._get_selected_asset_id()
        if not asset_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn một video trong bảng để soạn bài.")
            return

        asset = self.media_repo.get_media_asset(asset_id)
        if asset:
            self.send_to_composer.emit({
                "media_id": asset["id"],
                "file_path": asset["local_path"],
                "duration": asset.get("duration", 0),
                "platform": asset.get("source_platform", "other"),
            })

    def _on_delete_selected(self) -> None:
        """AC-12: Chặn xóa video nếu đang được một lịch đăng chờ tham chiếu."""
        asset_id = self._get_selected_asset_id()
        if not asset_id:
            QMessageBox.warning(self, "Chưa chọn", "Vui lòng chọn video cần xóa.")
            return

        # Kiểm tra tham chiếu lịch đăng chờ
        refs = self.media_repo.check_media_references(asset_id)
        if refs["active_job_count"] > 0:
            count = refs["active_job_count"]
            QMessageBox.critical(
                self,
                "Không thể xóa video (AC-12)",
                f"Video này hiện đang được {count} lịch đăng chờ thực hiện tham chiếu.\n"
                "Hành động xóa bị chặn để bảo vệ tính toàn vẹn của lịch đăng.\n"
                "Vui lòng hủy hoặc thay đổi các lịch liên quan trước khi xóa file.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận xóa",
            "Bạn có chắc chắn muốn xóa bản ghi video này khỏi thư viện không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.media_repo.delete_media_asset(asset_id, force=False, remove_file=False)
            self.reload_media_list()


class VideoWorkspaceView(QWidget):
    """Màn hình làm việc Video tổng hợp (gồm 2 tab)."""

    send_to_composer = Signal(dict)

    def __init__(
        self,
        downloader: VideoDownloader,
        media_repo: MediaRepository,
        media_processor: MediaProcessor,
        download_dir: Path,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self.tab_widget = QTabWidget()

        self.tab_download = VideoDownloadTab(
            downloader=downloader,
            media_repo=media_repo,
            media_processor=media_processor,
            download_dir=download_dir,
        )
        self.tab_library = MediaLibraryTab(media_repo=media_repo)

        # Nối tín hiệu làm mới thư viện khi tải xong
        self.tab_download.media_downloaded.connect(self.tab_library.reload_media_list)

        # Nối tín hiệu 1-click soạn bài từ cả 2 tab
        self.tab_download.send_to_composer.connect(self.send_to_composer.emit)
        self.tab_library.send_to_composer.connect(self.send_to_composer.emit)

        self.tab_widget.addTab(self.tab_download, "📥 Tải video mới (Đơn & Hàng loạt)")
        self.tab_widget.addTab(self.tab_library, "📂 Thư viện media đã tải")

        layout.addWidget(self.tab_widget)

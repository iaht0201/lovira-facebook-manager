"""
Lovira-Facebook Manager
Hộp thoại Tạo bài viết nhanh dạng Popup (QuickPostDialog)
- Mở nhanh tại bất kỳ màn hình nào qua nút 'Tạo bài nhanh' ở Header
- Chọn nhiều Fanpage đích đồng thời
- Đính kèm video (chọn file máy, chọn từ kho, dán link)
- Lên lịch theo giờ Việt Nam hoặc Đăng ngay
"""

import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QCheckBox,
    QScrollArea,
    QDateTimeEdit,
    QFrame,
    QFileDialog,
    QMessageBox,
)
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.domain.composer import ContentSnapshot
from src.lovira.domain.timezone import vn_now, vn_datetime_to_utc_iso, create_vn_datetime


class QuickPostDialog(QDialog):
    """Hộp thoại Tạo bài nhanh đa Page dạng Popup."""

    post_created = Signal()

    def __init__(
        self,
        page_repo: PageRepository,
        queue_repo: PublishQueueRepository,
        media_repo: Optional[MediaRepository] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.page_repo = page_repo
        self.queue_repo = queue_repo
        self.media_repo = media_repo

        self.setWindowTitle("Tạo bài viết nhanh và Đặt lịch đa Fanpage")
        self.resize(850, 680)
        self.setMinimumSize(750, 580)

        self.attached_video_path: Optional[str] = None
        self.attached_media_id: Optional[str] = None
        self.page_checkboxes: Dict[str, QCheckBox] = {}

        self._init_ui()
        self._load_pages()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Tiêu đề Popup
        title_box = QHBoxLayout()
        title_lbl = QLabel("➕ TẠO BÀI VIẾT VÀ ĐẶT LỊCH NHANH")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #818CF8;")
        title_box.addWidget(title_lbl)
        title_box.addStretch()
        layout.addLayout(title_box)

        # 1. Khung Chọn Fanpage đích (Ngang)
        pages_frame = QFrame()
        pages_frame.setObjectName("cardFrame")
        pages_layout = QVBoxLayout(pages_frame)
        pages_layout.setSpacing(8)

        pages_head = QHBoxLayout()
        lbl_target = QLabel("Fanpage đích:")
        lbl_target.setStyleSheet("font-weight: 600; color: #F8FAFC;")
        pages_head.addWidget(lbl_target)

        btn_select_all = QPushButton("Chọn tất cả")
        btn_select_all.setFixedHeight(26)
        btn_select_all.clicked.connect(self._select_all_pages)
        pages_head.addWidget(btn_select_all)

        btn_deselect_all = QPushButton("Bỏ chọn")
        btn_deselect_all.setFixedHeight(26)
        btn_deselect_all.clicked.connect(self._deselect_all_pages)
        pages_head.addWidget(btn_deselect_all)
        pages_head.addStretch()
        pages_layout.addLayout(pages_head)

        # Vùng cuộn checkbox Page
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(100)
        self.pages_container = QWidget()
        self.pages_grid = QHBoxLayout(self.pages_container)
        self.pages_grid.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(self.pages_container)
        pages_layout.addWidget(scroll)

        layout.addWidget(pages_frame)

        # 2. Khung Nhập Nội dung & Video
        content_frame = QFrame()
        content_frame.setObjectName("cardFrame")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setSpacing(10)

        content_layout.addWidget(QLabel("Nội dung bài viết / Caption Reels:"))
        self.caption_edit = QTextEdit()
        self.caption_edit.setPlaceholderText("Nhập caption hoặc hashtag chia sẻ lên Fanpage...")
        self.caption_edit.setFixedHeight(110)
        content_layout.addWidget(self.caption_edit)

        # Đính kèm Video
        media_row = QHBoxLayout()
        self.lbl_media_attached = QLabel("Chưa đính kèm video (Nếu là bài viết thông thường có thể bỏ qua)")
        self.lbl_media_attached.setStyleSheet("color: #94A3B8; font-size: 12px;")

        btn_pick_file = QPushButton("📁 Chọn file video")
        btn_pick_file.clicked.connect(self._pick_video_file)

        btn_clear_media = QPushButton("✖ Xóa video")
        btn_clear_media.clicked.connect(self._clear_attached_video)

        media_row.addWidget(self.lbl_media_attached, 1)
        media_row.addWidget(btn_pick_file)
        media_row.addWidget(btn_clear_media)
        content_layout.addLayout(media_row)

        layout.addWidget(content_frame)

        # 3. Khung Thời gian & Hẹn giờ Việt Nam
        sched_frame = QFrame()
        sched_frame.setObjectName("cardFrame")
        sched_layout = QHBoxLayout(sched_frame)
        sched_layout.setSpacing(14)

        self.cb_enable_schedule = QCheckBox("Bật Hẹn giờ đăng")
        self.cb_enable_schedule.setChecked(False)
        self.cb_enable_schedule.toggled.connect(self._on_schedule_toggled)
        sched_layout.addWidget(self.cb_enable_schedule)

        self.lbl_tz = QLabel("Giờ Việt Nam (UTC+7):")
        self.lbl_tz.setStyleSheet("color: #94A3B8; font-size: 12px;")
        self.lbl_tz.setVisible(False)
        sched_layout.addWidget(self.lbl_tz)

        self.datetime_edit = QDateTimeEdit()
        self.datetime_edit.setDisplayFormat("dd/MM/yyyy HH:mm")
        now_vn = vn_now() + timedelta(minutes=30)
        self.datetime_edit.setDateTime(QDateTime(now_vn.year, now_vn.month, now_vn.day, now_vn.hour, now_vn.minute, 0))
        self.datetime_edit.setVisible(False)
        sched_layout.addWidget(self.datetime_edit)

        sched_layout.addStretch()
        layout.addWidget(sched_frame)

        # 4. Nút bấm cuối cùng
        bottom_row = QHBoxLayout()
        self.btn_cancel = QPushButton("Hủy bỏ")
        self.btn_cancel.clicked.connect(self.reject)

        self.btn_submit = QPushButton("🚀 Đăng ngay lên 0 Page")
        self.btn_submit.setObjectName("primaryButton")
        self.btn_submit.clicked.connect(self._handle_submit)

        bottom_row.addStretch()
        bottom_row.addWidget(self.btn_cancel)
        bottom_row.addWidget(self.btn_submit)
        layout.addLayout(bottom_row)

    def _load_pages(self) -> None:
        pages = self.page_repo.list_pages()
        for p in pages:
            cb = QCheckBox(f"{p['name']} ({p['facebook_page_id']})")
            cb.setProperty("page_id", p["id"])
            cb.setChecked(True)
            cb.toggled.connect(self._update_submit_button_label)
            self.pages_grid.addWidget(cb)
            self.page_checkboxes[p["id"]] = cb
        self._update_submit_button_label()

    def _select_all_pages(self) -> None:
        for cb in self.page_checkboxes.values():
            cb.setChecked(True)
        self._update_submit_button_label()

    def _deselect_all_pages(self) -> None:
        for cb in self.page_checkboxes.values():
            cb.setChecked(False)
        self._update_submit_button_label()

    def _on_schedule_toggled(self, checked: bool) -> None:
        self.lbl_tz.setVisible(checked)
        self.datetime_edit.setVisible(checked)
        self._update_submit_button_label()

    def _update_submit_button_label(self) -> None:
        selected_count = sum(1 for cb in self.page_checkboxes.values() if cb.isChecked())
        if self.cb_enable_schedule.isChecked():
            self.btn_submit.setText(f"📅 Đặt lịch cho {selected_count} Page")
        else:
            self.btn_submit.setText(f"🚀 Đăng ngay lên {selected_count} Page")

    def _pick_video_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file video", "", "Video Files (*.mp4 *.mov *.avi *.mkv)"
        )
        if file_path:
            self.attached_video_path = file_path
            self.lbl_media_attached.setText(f"🎬 Đã đính kèm: {Path(file_path).name}")
            self.lbl_media_attached.setStyleSheet("color: #10B981; font-weight: 600; font-size: 12px;")

    def _clear_attached_video(self) -> None:
        self.attached_video_path = None
        self.attached_media_id = None
        self.lbl_media_attached.setText("Chưa đính kèm video")
        self.lbl_media_attached.setStyleSheet("color: #94A3B8; font-size: 12px;")

    def attach_video(self, file_path: str, media_id: Optional[str] = None) -> None:
        """Gắn sẵn video từ bên ngoài (khi 1-click từ video downloader)."""
        self.attached_video_path = file_path
        self.attached_media_id = media_id
        self.lbl_media_attached.setText(f"🎬 Đã đính kèm: {Path(file_path).name}")
        self.lbl_media_attached.setStyleSheet("color: #10B981; font-weight: 600; font-size: 12px;")

    def _handle_submit(self) -> None:
        selected_page_ids = [pid for pid, cb in self.page_checkboxes.items() if cb.isChecked()]
        if not selected_page_ids:
            QMessageBox.warning(self, "Chưa chọn Page", "Vui lòng chọn ít nhất một Fanpage đích.")
            return

        caption = self.caption_edit.toPlainText().strip()
        if not caption and not self.attached_video_path:
            QMessageBox.warning(self, "Thiếu nội dung", "Vui lòng nhập caption hoặc đính kèm video.")
            return

        is_scheduled = self.cb_enable_schedule.isChecked()
        sched_utc = None
        sched_mode = "instant"

        if is_scheduled:
            qdt = self.datetime_edit.dateTime()
            dt_vn = create_vn_datetime(
                qdt.date().year(), qdt.date().month(), qdt.date().day(),
                qdt.time().hour(), qdt.time().minute(), 0
            )
            now_vn = vn_now()
            if dt_vn <= now_vn + timedelta(minutes=1):
                QMessageBox.warning(self, "Thời gian không hợp lệ", "Thời gian hẹn giờ phải ở tương lai (ít nhất 2 phút nữa).")
                return
            sched_utc = vn_datetime_to_utc_iso(dt_vn)
            sched_mode = "scheduled_local"

        content_type = "reels" if self.attached_video_path else "text"
        import uuid
        batch_id = f"batch_{uuid.uuid4().hex[:10]}"
        now_utc = vn_datetime_to_utc_iso(vn_now())
        target_sched_utc = sched_utc if is_scheduled else now_utc

        from src.lovira.domain.composer import ContentType, ScheduleMode

        snapshots = []
        for pid in selected_page_ids:
            snap = ContentSnapshot(
                batch_id=batch_id,
                page_id=pid,
                content_type=ContentType.REELS if self.attached_video_path else ContentType.TEXT,
                final_caption=caption,
                primary_media_id=self.attached_media_id,
                media_path=self.attached_video_path,
                scheduled_at_utc=target_sched_utc,
                schedule_mode=ScheduleMode.LOCAL,
            )
            snapshots.append(snap)

        client_req_id = f"quick_{uuid.uuid4().hex[:12]}"

        # Enqueue hàng đợi nguyên tử
        self.queue_repo.enqueue_batch(
            client_request_id=client_req_id,
            snapshots=snapshots,
        )

        msg = f"Đã lên lịch thành công cho {len(selected_page_ids)} Fanpage!" if is_scheduled else f"Đã thêm vào hàng đợi đăng ngay cho {len(selected_page_ids)} Fanpage!"
        QMessageBox.information(self, "Thành công", msg)
        self.post_created.emit()
        self.accept()

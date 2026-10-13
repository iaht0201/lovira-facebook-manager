"""
Lovira Workspace 2.0 — Post Composer Workspace (post_composer.py)
Giao diện Soạn bài, Facebook Reels và Đặt lịch đa Fanpage 2.0 (Mockup 03_soan_bai.png):
- Thiết kế bố cục 2 cột: Cột Soạn thảo nâng cao & Khung Live Preview di động thời gian thực
- Hỗ trợ đăng đồng thời đa Page kèm bộ chọn nhanh (Select All / Deselect All)
- Tích hợp SimulatedPostPreview hiển thị trực quan Reels/Post trên điện thoại
- Bộ đếm ký tự, đếm hashtag và thanh công cụ chèn hashtag nhanh
- Hẹn giờ chuẩn hóa theo múi giờ Việt Nam (UTC+7), bảo lưu giờ khi bật/tắt (AC-06, AC-41)
- Tạo ContentSnapshot bất biến và hàng đợi nguyên tử chống bấm đúp (AC-15, AC-19)
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from PySide6.QtCore import Qt, Signal, QDateTime
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QFrame,
    QScrollArea,
    QMessageBox,
    QGroupBox,
    QListWidget,
    QListWidgetItem,
)
from src.lovira.domain.timezone import vn_now, vn_datetime_to_utc_iso, format_vn_display
from src.lovira.domain.composer import (
    PostComposerState,
    ContentType,
    ScheduleMode,
    ContentSnapshot,
)
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.widgets.simulated_preview import SimulatedPostPreview

logger = logging.getLogger(__name__)


class PostComposerView(QWidget):
    """Giao diện Soạn bài, Facebook Reels và Đặt lịch đa Page 2.0."""

    publish_enqueued = Signal(list)  # Phát danh sách job_id khi đã lưu hàng đợi thành công

    def __init__(
        self,
        page_repo: PageRepository,
        queue_repo: PublishQueueRepository,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.page_repo = page_repo
        self.queue_repo = queue_repo
        self.composer_state = PostComposerState()

        # Dữ liệu media đính kèm hiện tại
        self.attached_media: Optional[Dict[str, Any]] = None

        self._init_ui()
        self.reload_pages()
        self._update_submit_button_label()

    def _init_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(20, 18, 20, 20)
        main_layout.setSpacing(18)

        # CỘT TRÁI: Form Soạn thảo (Scrollable)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        form_layout = QVBoxLayout(container)
        form_layout.setContentsMargins(0, 0, 8, 0)
        form_layout.setSpacing(16)

        # 1. Chọn Fanpage đích
        page_box = QGroupBox("1. Chọn Fanpage đích (Đăng đồng thời đa Page)")
        page_layout = QVBoxLayout(page_box)
        page_layout.setSpacing(10)

        # Header hàng nút chọn nhanh
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(8)
        lbl_hint = QLabel("Tích chọn các Fanpage bạn muốn xuất bản bài viết:")
        lbl_hint.setStyleSheet("font-size: 11px; color: #94A3B8;")
        btn_bar.addWidget(lbl_hint)
        btn_bar.addStretch()

        self.btn_select_all = QPushButton("Chọn tất cả")
        self.btn_select_all.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.btn_select_all.clicked.connect(self._select_all_pages)
        btn_bar.addWidget(self.btn_select_all)

        self.btn_deselect_all = QPushButton("Bỏ chọn")
        self.btn_deselect_all.setStyleSheet("font-size: 11px; padding: 3px 8px;")
        self.btn_deselect_all.clicked.connect(self._deselect_all_pages)
        btn_bar.addWidget(self.btn_deselect_all)
        page_layout.addLayout(btn_bar)

        self.page_list_widget = QListWidget()
        self.page_list_widget.setMaximumHeight(140)
        self.page_list_widget.itemChanged.connect(self._on_page_selection_changed)
        page_layout.addWidget(self.page_list_widget)

        form_layout.addWidget(page_box)

        # 2. Loại nội dung & Media đính kèm
        content_box = QGroupBox("2. Định dạng nội dung & Media")
        content_layout = QVBoxLayout(content_box)
        content_layout.setSpacing(10)

        type_row = QHBoxLayout()
        type_row.addWidget(QLabel("Định dạng xuất bản:"))
        self.cb_content_type = QComboBox()
        self.cb_content_type.addItems(["Reels", "Video", "Chữ (Text)", "Hình ảnh"])
        self.cb_content_type.currentTextChanged.connect(self._on_content_type_changed)
        type_row.addWidget(self.cb_content_type)
        type_row.addStretch()
        content_layout.addLayout(type_row)

        # Thẻ thông tin media đính kèm
        self.media_card = QFrame()
        self.media_card.setObjectName("cardFrame")
        media_card_layout = QHBoxLayout(self.media_card)
        media_card_layout.setContentsMargins(12, 10, 12, 10)

        self.lbl_media_icon = QLabel()
        self.lbl_media_icon.setPixmap(get_icon("video", "#6258E8", 20).pixmap(20, 20))
        media_card_layout.addWidget(self.lbl_media_icon)

        self.lbl_media_info = QLabel("Chưa có media nào được đính kèm.")
        self.lbl_media_info.setStyleSheet("color: #94A3B8; font-size: 12px;")
        media_card_layout.addWidget(self.lbl_media_info, stretch=1)

        self.btn_clear_media = QPushButton("Gỡ media")
        self.btn_clear_media.setStyleSheet("background: transparent; border: 1px solid #F0707B; color: #F0707B; border-radius: 4px; padding: 3px 8px; font-size: 11px;")
        self.btn_clear_media.setVisible(False)
        self.btn_clear_media.clicked.connect(self._clear_attached_media)
        media_card_layout.addWidget(self.btn_clear_media)

        content_layout.addWidget(self.media_card)
        form_layout.addWidget(content_box)

        # 3. Soạn Caption (Nội dung bài viết)
        caption_box = QGroupBox("3. Nội dung bài viết / Caption Reels")
        caption_layout = QVBoxLayout(caption_box)
        caption_layout.setSpacing(8)

        # Thanh công cụ chèn hashtag nhanh
        tools_row = QHBoxLayout()
        tools_row.setSpacing(6)
        lbl_quick_tag = QLabel("Gợi ý hashtag:")
        lbl_quick_tag.setStyleSheet("font-size: 11px; color: #64748B;")
        tools_row.addWidget(lbl_quick_tag)

        sample_tags = ["#reels", "#trending", "#viral", "#review", "#fbtools"]
        for tag in sample_tags:
            btn_tag = QPushButton(tag)
            btn_tag.setStyleSheet("""
                QPushButton {
                    background-color: #1E2A44;
                    color: #6258E8;
                    border: 1px solid #2B3A5A;
                    border-radius: 4px;
                    padding: 2px 6px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #273656;
                    border-color: #6258E8;
                }
            """)
            btn_tag.clicked.connect(lambda _, t=tag: self._append_hashtag(t))
            tools_row.addWidget(btn_tag)

        tools_row.addStretch()
        caption_layout.addLayout(tools_row)

        self.caption_input = QTextEdit()
        self.caption_input.setPlaceholderText("Nhập nội dung bài viết, tiêu đề Reels, hashtag xu hướng...")
        self.caption_input.setMinimumHeight(110)
        self.caption_input.textChanged.connect(self._on_caption_changed)
        caption_layout.addWidget(self.caption_input)

        # Bộ đếm ký tự & hashtag
        self.lbl_char_count = QLabel("0 ký tự | 0 hashtag")
        self.lbl_char_count.setStyleSheet("font-size: 11px; color: #64748B; text-align: right;")
        self.lbl_char_count.setAlignment(Qt.AlignmentFlag.AlignRight)
        caption_layout.addWidget(self.lbl_char_count)

        form_layout.addWidget(caption_box)

        # 4. Hẹn giờ theo múi giờ Việt Nam (UTC+7)
        schedule_box = QGroupBox("4. Thời gian đăng bài (Múi giờ Việt Nam — UTC+7)")
        schedule_layout = QVBoxLayout(schedule_box)
        schedule_layout.setSpacing(10)

        self.chk_schedule = QCheckBox("Bật hẹn giờ tự động (Hệ thống sẽ chạy đăng nền trên máy)")
        self.chk_schedule.setChecked(False)
        self.chk_schedule.toggled.connect(self._on_schedule_toggled)
        schedule_layout.addWidget(self.chk_schedule)

        # Vùng chọn ngày giờ
        self.schedule_picker_frame = QFrame()
        picker_layout = QHBoxLayout(self.schedule_picker_frame)
        picker_layout.setContentsMargins(0, 4, 0, 0)
        picker_layout.setSpacing(10)

        picker_layout.addWidget(QLabel("Thời điểm:"))
        self.datetime_picker = QDateTimeEdit()
        self.datetime_picker.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.datetime_picker.setCalendarPopup(True)

        # Khởi tạo mặc định: Giờ Việt Nam hiện tại + 1 tiếng
        init_time = vn_now() + timedelta(hours=1)
        self.datetime_picker.setDateTime(
            QDateTime(init_time.year, init_time.month, init_time.day, init_time.hour, init_time.minute, 0)
        )
        self.datetime_picker.dateTimeChanged.connect(self._on_datetime_changed)
        picker_layout.addWidget(self.datetime_picker)

        self.lbl_schedule_summary = QLabel()
        self.lbl_schedule_summary.setStyleSheet("color: #24C89A; font-weight: 600; font-size: 12px;")
        picker_layout.addWidget(self.lbl_schedule_summary)
        picker_layout.addStretch()

        self.schedule_picker_frame.setVisible(False)
        schedule_layout.addWidget(self.schedule_picker_frame)
        form_layout.addWidget(schedule_box)

        # 5. Khung Tóm tắt & Nút Thực hiện xuất bản
        summary_frame = QFrame()
        summary_frame.setObjectName("cardFrame")
        summary_layout = QVBoxLayout(summary_frame)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        summary_layout.setSpacing(10)

        self.lbl_summary_text = QLabel("Tóm tắt: Đang chuẩn bị bài viết...")
        self.lbl_summary_text.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: 600;")
        summary_layout.addWidget(self.lbl_summary_text)

        action_row = QHBoxLayout()
        action_row.addStretch()

        self.btn_submit = QPushButton("🚀 Đăng ngay lên 0 Page")
        self.btn_submit.setObjectName("primaryButton")
        self.btn_submit.setStyleSheet("font-size: 14px; font-weight: 700; padding: 10px 24px;")
        self.btn_submit.clicked.connect(self._handle_submit)
        action_row.addWidget(self.btn_submit)

        summary_layout.addLayout(action_row)
        form_layout.addWidget(summary_frame)

        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area, stretch=3)

        # CỘT PHẢI: Khung Live Simulated Preview
        self.preview_widget = SimulatedPostPreview(self)
        main_layout.addWidget(self.preview_widget, stretch=2)

        self._update_schedule_display()

    def reload_pages(self) -> None:
        """Tải danh sách các Fanpage có trong cơ sở dữ liệu local."""
        self.page_list_widget.clear()
        pages = self.page_repo.list_pages()
        for p in pages:
            item = QListWidgetItem(f"📄  {p['name']} (ID: {p['facebook_page_id']})")
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.page_list_widget.addItem(item)
        self._update_live_preview()

    def _select_all_pages(self) -> None:
        for i in range(self.page_list_widget.count()):
            self.page_list_widget.item(i).setCheckState(Qt.CheckState.Checked)

    def _deselect_all_pages(self) -> None:
        for i in range(self.page_list_widget.count()):
            self.page_list_widget.item(i).setCheckState(Qt.CheckState.Unchecked)

    def _append_hashtag(self, tag: str) -> None:
        current = self.caption_input.toPlainText()
        if current and not current.endswith(" ") and not current.endswith("\n"):
            current += " "
        self.caption_input.setPlainText(current + tag + " ")
        self.caption_input.moveCursor(self.caption_input.textCursor().MoveOperation.End)

    def attach_video_data(self, media_data: Dict[str, Any]) -> None:
        """Tiếp nhận dữ liệu video từ tab Tải video hoặc Thư viện (1-click flow)."""
        self.attached_media = media_data
        file_path = media_data.get("file_path", "")
        file_name = file_path.split("/")[-1].split("\\")[-1]
        self.lbl_media_info.setText(f"🎬 Video: {file_name} (ID: {media_data.get('media_id')})")
        self.btn_clear_media.setVisible(True)

        # Gợi ý caption nếu có tiêu đề video
        if media_data.get("title") and not self.caption_input.toPlainText():
            self.caption_input.setPlainText(media_data["title"])

        # Mặc định chọn Reels
        self.cb_content_type.setCurrentText("Reels")
        self._update_summary()
        self._update_live_preview()

    def _clear_attached_media(self) -> None:
        self.attached_media = None
        self.lbl_media_info.setText("Chưa có media nào được đính kèm.")
        self.btn_clear_media.setVisible(False)
        self._update_summary()
        self._update_live_preview()

    def _get_selected_page_ids(self) -> List[str]:
        selected = []
        for i in range(self.page_list_widget.count()):
            item = self.page_list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def _on_page_selection_changed(self, _) -> None:
        self._update_submit_button_label()
        self._update_summary()
        self._update_live_preview()

    def _on_content_type_changed(self, text: str) -> None:
        type_map = {
            "Reels": ContentType.REELS,
            "Video": ContentType.VIDEO,
            "Chữ (Text)": ContentType.TEXT,
            "Hình ảnh": ContentType.PHOTO,
        }
        self.composer_state.content_type = type_map.get(text, ContentType.REELS)
        self._update_summary()
        self._update_live_preview()

    def _on_caption_changed(self) -> None:
        caption = self.caption_input.toPlainText()
        self.composer_state.common_caption = caption

        # Đếm ký tự và hashtag
        words = caption.split()
        hashtags = [w for w in words if w.startswith("#") and len(w) > 1]
        self.lbl_char_count.setText(f"{len(caption)} ký tự | {len(hashtags)} hashtags")

        self._update_summary()
        self._update_live_preview()

    def _on_schedule_toggled(self, checked: bool) -> None:
        """
        AC-06 & AC-41:
        - Bật: hiển thị datetime picker.
        - Tắt: ẩn datetime picker nhưng KHÔNG xóa giờ đã chọn, KHÔNG tự động đăng bài!
        """
        self.composer_state.is_scheduled = checked
        self.schedule_picker_frame.setVisible(checked)
        self._update_submit_button_label()
        self._update_summary()

    def _on_datetime_changed(self, qdt: QDateTime) -> None:
        py_dt = qdt.toPython()
        self.composer_state.scheduled_vn_datetime = py_dt
        self._update_schedule_display()
        self._update_summary()

    def _update_schedule_display(self) -> None:
        qdt = self.datetime_picker.dateTime().toPython()
        vn_str = format_vn_display(qdt)
        utc_iso = vn_datetime_to_utc_iso(qdt)
        self.lbl_schedule_summary.setText(f"➔ {vn_str} [UTC: {utc_iso}]")

    def _update_submit_button_label(self) -> None:
        count = len(self._get_selected_page_ids())
        if self.chk_schedule.isChecked():
            self.btn_submit.setText(f"📅 Đặt lịch cho {count} Page")
        else:
            self.btn_submit.setText(f"🚀 Đăng ngay lên {count} Page")

    def _update_summary(self) -> None:
        pages = self._get_selected_page_ids()
        c_type = self.cb_content_type.currentText()
        if not pages:
            self.lbl_summary_text.setText("⚠️ Chưa chọn Fanpage đích nào.")
            return

        mode_str = "Hẹn giờ tự động" if self.chk_schedule.isChecked() else "Đăng ngay lập tức"
        media_str = "Có video gắn kèm" if self.attached_media else "Không có file đính kèm"
        self.lbl_summary_text.setText(
            f"Tóm tắt: Đăng {c_type} lên {len(pages)} Fanpage ({mode_str}) — {media_str}."
        )

    def _update_live_preview(self) -> None:
        """Đồng bộ hóa dữ liệu thời gian thực sang cột Preview di động."""
        pages = self._get_selected_page_ids()
        page_name = ""
        if pages:
            p_obj = self.page_repo.get_page(pages[0])
            if p_obj:
                page_name = p_obj.get("name", "")

        caption = self.caption_input.toPlainText()
        media_path = self.attached_media.get("file_path") if self.attached_media else None
        c_type = self.cb_content_type.currentText()

        self.preview_widget.update_preview(
            page_name=page_name,
            caption=caption,
            media_path=media_path,
            content_type=c_type,
        )

    def _handle_submit(self) -> None:
        """
        Quy trình Đăng / Đặt lịch:
        - Xác thực input
        - Tạo ContentSnapshot bất biến (AC-19)
        - Enqueue batch nguyên tử với client_request_id (AC-15)
        """
        selected_pages = self._get_selected_page_ids()
        if not selected_pages:
            QMessageBox.warning(self, "Chưa chọn Page", "Vui lòng chọn ít nhất một Fanpage đích.")
            return

        c_type = self.composer_state.content_type
        caption = self.caption_input.toPlainText().strip()

        # Kiểm tra yêu cầu media cho Reels / Video
        if c_type in (ContentType.REELS, ContentType.VIDEO) and not self.attached_media:
            QMessageBox.warning(self, "Thiếu video", f"Định dạng {c_type.value.upper()} bắt buộc phải có video đính kèm.")
            return

        # Thời gian đăng
        is_scheduled = self.chk_schedule.isChecked()
        schedule_mode = ScheduleMode.LOCAL if is_scheduled else ScheduleMode.LOCAL
        scheduled_utc = vn_datetime_to_utc_iso(self.datetime_picker.dateTime().toPython()) if is_scheduled else vn_datetime_to_utc_iso(vn_now())

        # Khóa nút tránh bấm liên tiếp (AC-15)
        self.btn_submit.setEnabled(False)
        self.btn_submit.setText("Đang khởi tạo tác vụ...")

        client_request_id = f"req_{uuid.uuid4().hex[:16]}"
        batch_id = f"batch_{uuid.uuid4().hex[:12]}"

        media_id = self.attached_media.get("media_id") if self.attached_media else None
        media_path = self.attached_media.get("file_path") if self.attached_media else None

        snapshots: List[ContentSnapshot] = []
        for p_id in selected_pages:
            snap = ContentSnapshot(
                batch_id=batch_id,
                page_id=p_id,
                content_type=c_type,
                final_caption=caption,
                primary_media_id=media_id,
                media_path=media_path,
                schedule_mode=schedule_mode,
                scheduled_at_utc=scheduled_utc,
            )
            snapshots.append(snap)

        try:
            job_ids = self.queue_repo.enqueue_batch(client_request_id, snapshots)
            action_desc = "đặt lịch" if is_scheduled else "đưa vào hàng đợi đăng ngay"
            QMessageBox.information(
                self,
                "Thành công",
                f"Đã {action_desc} thành công cho {len(job_ids)} Fanpage!\n"
                f"Mã nhóm công việc: {batch_id}",
            )
            self.publish_enqueued.emit(job_ids)

            # Xóa form sau khi gửi thành công
            self.caption_input.clear()
            self._clear_attached_media()
        except Exception as e:
            QMessageBox.critical(self, "Lỗi đăng bài", f"Không thể khởi tạo công việc đăng bài: {e}")
        finally:
            self.btn_submit.setEnabled(True)
            self._update_submit_button_label()

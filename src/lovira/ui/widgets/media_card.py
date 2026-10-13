"""
Lovira Workspace 2.0 — MediaThumbnailCard Primitive
Thẻ hiển thị Media trong Thư viện (Section 4.S05, Mockup 05):
- Hiển thị thumbnail kèm thời lượng video overlay
- Huy hiệu nền tảng nguồn (TikTok, Douyin, Bilibili, Local)
- Nút hành động nhanh: Gửi sang Soạn bài, Xem trước, Xóa
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
)

from src.lovira.ui.design.icons import get_icon


class MediaThumbnailCard(QFrame):
    """Thẻ hiển thị thông tin media trong Thư viện."""

    send_to_composer_requested = Signal(dict)
    preview_requested = Signal(dict)
    delete_requested = Signal(dict)

    def __init__(self, media_data: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.media_data = media_data
        self.setObjectName("cardFrame")
        self.setFixedWidth(260)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 1. Khung Thumbnail 16:9
        thumb_container = QFrame()
        thumb_container.setFixedHeight(140)
        thumb_container.setStyleSheet("background-color: #0B1220; border-radius: 8px;")
        thumb_layout = QVBoxLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)

        # Ảnh thumbnail hoặc icon video mặc định
        self.lbl_thumb = QLabel()
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_path = self.media_data.get("thumbnail_path")
        if thumb_path:
            px = QPixmap(str(thumb_path))
            if not px.isNull():
                self.lbl_thumb.setPixmap(px.scaled(260, 140, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
            else:
                self.lbl_thumb.setPixmap(get_icon("video", "#6258E8", 36).pixmap(36, 36))
        else:
            self.lbl_thumb.setPixmap(get_icon("video", "#6258E8", 36).pixmap(36, 36))
        thumb_layout.addWidget(self.lbl_thumb)

        # Thời lượng video overlay
        duration = float(self.media_data.get("duration", 0.0) or 0.0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        dur_str = f"{mins:02d}:{secs:02d}"

        lbl_dur = QLabel(dur_str)
        lbl_dur.setStyleSheet("""
            background-color: rgba(11, 18, 32, 0.85);
            color: #F3F6FC;
            font-size: 11px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
        """)
        lbl_dur.setAlignment(Qt.AlignmentFlag.AlignRight)
        thumb_layout.addWidget(lbl_dur, alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)

        layout.addWidget(thumb_container)

        # 2. Thông tin chi tiết (Tiêu đề, Platform, Kích thước)
        title = self.media_data.get("title") or self.media_data.get("local_path", "Video")
        if "/" in str(title) or "\\" in str(title):
            title = str(title).replace("\\", "/").split("/")[-1]

        self.lbl_title = QLabel(str(title))
        self.lbl_title.setStyleSheet("font-size: 13px; font-weight: 600; color: #F3F6FC;")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setMaximumHeight(36)
        layout.addWidget(self.lbl_title)

        # Meta tags row
        meta_row = QHBoxLayout()
        meta_row.setSpacing(6)

        platform = self.media_data.get("source_platform", "local").upper()
        lbl_plat = QLabel(platform)
        lbl_plat.setStyleSheet("color: #818CF8; font-size: 11px; font-weight: 600;")
        meta_row.addWidget(lbl_plat)

        size_mb = (self.media_data.get("size_bytes", 0) or 0) / (1024 * 1024)
        lbl_size = QLabel(f"{size_mb:.1f} MB")
        lbl_size.setStyleSheet("color: #64748B; font-size: 11px;")
        meta_row.addWidget(lbl_size)

        meta_row.addStretch()
        layout.addLayout(meta_row)

        # 3. Nút hành động nhanh
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_preview = QPushButton("Xem")
        self.btn_preview.setFixedHeight(30)
        self.btn_preview.setIcon(get_icon("video", "#F3F6FC", 14))
        self.btn_preview.clicked.connect(lambda: self.preview_requested.emit(self.media_data))
        btn_row.addWidget(self.btn_preview)

        self.btn_compose = QPushButton("Soạn bài")
        self.btn_compose.setObjectName("primaryButton")
        self.btn_compose.setFixedHeight(30)
        self.btn_compose.setIcon(get_icon("composer", "#FFFFFF", 14))
        self.btn_compose.clicked.connect(lambda: self.send_to_composer_requested.emit(self.media_data))
        btn_row.addWidget(self.btn_compose)

        layout.addLayout(btn_row)

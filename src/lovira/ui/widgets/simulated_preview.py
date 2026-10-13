"""
Lovira Workspace 2.0 — SimulatedPostPreview Widget
Khung xem trước mô phỏng giao diện Facebook Reels / Post trên di động thời gian thực (Live Preview):
- Tự động cập nhật tiêu đề Fanpage, caption, hashtag và hình thu nhỏ video
- Hiển thị tỷ lệ chuẩn khung hình di động (Reels 9:16 hoặc Post chuẩn)
- Tích hợp các nút tương tác mô phỏng chân thực (Like, Comment, Share, Audio)
"""

from typing import Optional
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from src.lovira.ui.design.icons import get_icon


class SimulatedPostPreview(QFrame):
    """Khung mô phỏng bài viết Facebook Reels thời gian thực."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        self.setFixedWidth(340)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 1. Header Khung Preview
        top_bar = QHBoxLayout()
        lbl_badge = QLabel("XEM TRƯỚC TRÊN DI ĐỘNG")
        lbl_badge.setStyleSheet("font-size: 11px; font-weight: 700; color: #6258E8; letter-spacing: 0.5px;")
        top_bar.addWidget(lbl_badge)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # 2. Khung Giả lập Điện thoại (Device Mockup Frame)
        self.phone_mockup = QFrame()
        self.phone_mockup.setStyleSheet("""
            QFrame {
                background-color: #0A0F1D;
                border: 2px solid #22314E;
                border-radius: 16px;
            }
        """)
        phone_layout = QVBoxLayout(self.phone_mockup)
        phone_layout.setContentsMargins(12, 12, 12, 12)
        phone_layout.setSpacing(10)

        # A. Page Header (Avatar + Tên Fanpage + Icon FB)
        page_header = QHBoxLayout()
        page_header.setSpacing(8)

        self.lbl_avatar = QLabel("P")
        self.lbl_avatar.setFixedSize(32, 32)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_avatar.setStyleSheet("""
            QLabel {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                border-radius: 16px;
            }
        """)
        page_header.addWidget(self.lbl_avatar)

        name_box = QVBoxLayout()
        name_box.setSpacing(2)
        self.lbl_page_name = QLabel("Chưa chọn Fanpage")
        self.lbl_page_name.setStyleSheet("font-size: 12px; font-weight: 700; color: #F3F6FC;")
        self.lbl_time_stamp = QLabel("Vừa xong • 🌐")
        self.lbl_time_stamp.setStyleSheet("font-size: 10px; color: #64748B;")
        name_box.addWidget(self.lbl_page_name)
        name_box.addWidget(self.lbl_time_stamp)
        page_header.addLayout(name_box)
        page_header.addStretch()

        # Logo Facebook nhỏ
        lbl_fb_badge = QLabel()
        lbl_fb_badge.setPixmap(get_icon("facebook", "#1877F2", 16).pixmap(16, 16))
        page_header.addWidget(lbl_fb_badge)

        phone_layout.addLayout(page_header)

        # B. Vùng Video / Media Container
        self.media_container = QFrame()
        self.media_container.setStyleSheet("""
            QFrame {
                background-color: #141D2D;
                border: 1px dashed #2E3E5B;
                border-radius: 10px;
                min-height: 240px;
            }
        """)
        media_layout = QVBoxLayout(self.media_container)
        media_layout.setContentsMargins(10, 10, 10, 10)
        media_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_media_icon = QLabel()
        self.lbl_media_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_media_icon.setPixmap(get_icon("play", "#6258E8", 36).pixmap(36, 36))
        media_layout.addWidget(self.lbl_media_icon)

        self.lbl_media_status = QLabel("Đính kèm video Reels để xem trước")
        self.lbl_media_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_media_status.setStyleSheet("color: #64748B; font-size: 11px;")
        self.lbl_media_status.setWordWrap(True)
        media_layout.addWidget(self.lbl_media_status)

        phone_layout.addWidget(self.media_container)

        # C. Caption Preview
        self.lbl_caption = QLabel("Nội dung bài viết sẽ hiển thị tại đây khi bạn nhập caption...")
        self.lbl_caption.setStyleSheet("font-size: 12px; color: #E2E8F0; line-height: 1.4;")
        self.lbl_caption.setWordWrap(True)
        self.lbl_caption.setMaximumHeight(80)
        phone_layout.addWidget(self.lbl_caption)

        # D. Mock Interactive Action Bar (Thích, Bình luận, Chia sẻ)
        action_bar = QHBoxLayout()
        action_bar.setSpacing(12)

        lbl_like = QLabel("👍 Thích")
        lbl_like.setStyleSheet("color: #94A3B8; font-size: 11px;")
        lbl_comment = QLabel("💬 Bình luận")
        lbl_comment.setStyleSheet("color: #94A3B8; font-size: 11px;")
        lbl_share = QLabel("↗️ Chia sẻ")
        lbl_share.setStyleSheet("color: #94A3B8; font-size: 11px;")

        action_bar.addWidget(lbl_like)
        action_bar.addWidget(lbl_comment)
        action_bar.addWidget(lbl_share)
        action_bar.addStretch()

        phone_layout.addLayout(action_bar)
        layout.addWidget(self.phone_mockup)

    def update_preview(
        self,
        page_name: str = "",
        caption: str = "",
        media_path: Optional[str] = None,
        content_type: str = "Reels",
    ) -> None:
        """Cập nhật dữ liệu mô phỏng theo thời gian thực."""
        # Cập nhật tên Page & Avatar chữ cái đầu
        clean_name = page_name.strip() if page_name else "Chưa chọn Fanpage"
        self.lbl_page_name.setText(clean_name)
        first_letter = clean_name[0].upper() if clean_name else "P"
        self.lbl_avatar.setText(first_letter)

        # Cập nhật caption
        if caption.strip():
            display_cap = caption.strip()
            if len(display_cap) > 140:
                display_cap = display_cap[:140] + "... Xem thêm"
            self.lbl_caption.setText(display_cap)
            self.lbl_caption.setStyleSheet("font-size: 12px; color: #F8FAFC; line-height: 1.4;")
        else:
            self.lbl_caption.setText("Nội dung bài viết sẽ hiển thị tại đây khi bạn nhập caption...")
            self.lbl_caption.setStyleSheet("font-size: 12px; color: #64748B; line-height: 1.4;")

        # Cập nhật media
        if media_path:
            p = Path(media_path)
            file_name = p.name
            self.lbl_media_icon.setPixmap(get_icon("video", "#24C89A", 40).pixmap(40, 40))
            self.lbl_media_status.setText(f"🎬 {content_type.upper()}: {file_name}")
            self.lbl_media_status.setStyleSheet("color: #24C89A; font-weight: 600; font-size: 11px;")
        else:
            self.lbl_media_icon.setPixmap(get_icon("play", "#6258E8", 36).pixmap(36, 36))
            self.lbl_media_status.setText(f"Đính kèm file để xem trước {content_type}")
            self.lbl_media_status.setStyleSheet("color: #64748B; font-size: 11px;")

"""
Lovira Workspace 2.0 — SimulatedPostPreview Widget
Khung xem trước mô phỏng giao diện Facebook Reels / Post trên di động thời gian thực (Live Preview):
- Tự động cập nhật tiêu đề Fanpage, caption, hashtag và hình thu nhỏ video
- Hiển thị tỷ lệ chuẩn khung hình di động (Reels 9:16 hoặc Post chuẩn)
- Bổ sung QPixmap hiển thị ảnh thực tế và khung hình thumbnail của video
- Tự động thu gọn vùng media khi loại bài là Văn bản thuần
- Tích hợp các nút tương tác mô phỏng chân thực (Like, Comment, Share)
"""

from typing import Optional
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from src.lovira.ui.design.icons import get_icon


class SimulatedPostPreview(QFrame):
    """Khung mô phỏng bài viết Facebook Reels / Post thời gian thực."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("cardFrame")
        self.setMinimumWidth(260)
        self.setMaximumWidth(310)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # 1. Header Khung Preview
        top_bar = QHBoxLayout()
        lbl_badge = QLabel("XEM TRƯỚC TRÊN DI ĐỘNG")
        lbl_badge.setStyleSheet("font-size: 11px; font-weight: 700; color: #6258E8; letter-spacing: 0.5px;")
        top_bar.addWidget(lbl_badge)
        top_bar.addStretch()
        layout.addLayout(top_bar)

        # 2. Khung Giả lập Điện thoại (Device Mockup Frame)
        self.phone_mockup = QFrame()
        self.phone_mockup.setObjectName("previewPhone")
        self.phone_mockup.setStyleSheet("""
            QFrame#previewPhone {
                background-color: #0A0F1D;
                border: 1px solid #293B58;
                border-radius: 14px;
            }
        """)
        phone_layout = QVBoxLayout(self.phone_mockup)
        phone_layout.setContentsMargins(10, 10, 10, 10)
        phone_layout.setSpacing(8)

        # A. Page Header (Avatar + Tên Fanpage + Icon FB)
        page_header = QHBoxLayout()
        page_header.setSpacing(8)

        self.lbl_avatar = QLabel("P")
        self.lbl_avatar.setFixedSize(30, 30)
        self.lbl_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_avatar.setStyleSheet("""
            QLabel {
                background-color: #6258E8;
                color: #FFFFFF;
                font-weight: 800;
                font-size: 12px;
                border-radius: 15px;
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
        self.media_container.setObjectName("previewMedia")
        self.media_container.setFixedHeight(160)
        self.media_container.setStyleSheet("""
            QFrame#previewMedia {
                background-color: #141D2D;
                border: 1px dashed #344763;
                border-radius: 10px;
            }
        """)
        media_layout = QVBoxLayout(self.media_container)
        media_layout.setContentsMargins(6, 6, 6, 6)
        media_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Label hiển thị hình ảnh thật (QPixmap)
        self.lbl_media_image = QLabel()
        self.lbl_media_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_media_image.setStyleSheet("border-radius: 8px;")
        self.lbl_media_image.hide()
        media_layout.addWidget(self.lbl_media_image)

        # Placeholder Icon
        self.lbl_media_icon = QLabel()
        self.lbl_media_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_media_icon.setPixmap(get_icon("play", "#6258E8", 32).pixmap(32, 32))
        media_layout.addWidget(self.lbl_media_icon)

        # Placeholder Status
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
        action_bar.setSpacing(10)

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

    def _resolve_pixmap(self, media_path: Path, thumbnail_path: Optional[str] = None) -> Optional[QPixmap]:
        """Tìm hoặc load QPixmap từ ảnh hoặc video thumbnail."""
        try:
            # 1. Nếu có thumbnail_path chỉ định rõ
            if thumbnail_path and Path(thumbnail_path).is_file():
                pm = QPixmap(str(thumbnail_path))
                if not pm.isNull():
                    return pm

            # 2. Nếu là ảnh trực tiếp
            img_exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
            if media_path.suffix.lower() in img_exts and media_path.is_file():
                pm = QPixmap(str(media_path))
                if not pm.isNull():
                    return pm

            # 3. Nếu là video, kiểm tra thumbnail đi kèm (ví dụ .thumb.jpg hoặc _thumb.jpg)
            for thumb_name in [
                media_path.with_suffix(".thumb.jpg"),
                media_path.with_suffix(".jpg"),
                media_path.parent / f"{media_path.stem}_thumb.jpg",
            ]:
                if thumb_name.is_file():
                    pm = QPixmap(str(thumb_name))
                    if not pm.isNull():
                        return pm
        except Exception:
            pass
        return None

    def update_preview(
        self,
        page_name: str = "",
        caption: str = "",
        media_path: Optional[str] = None,
        content_type: str = "Reels",
        thumbnail_path: Optional[str] = None,
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

        # Xử lý theo từng ContentType
        is_text = content_type in ("Văn bản", "text")
        if is_text:
            self.media_container.hide()
            return

        self.media_container.show()

        pixmap = None
        if media_path:
            p = Path(media_path)
            pixmap = self._resolve_pixmap(p, thumbnail_path)
            file_name = p.name

            if pixmap and not pixmap.isNull():
                scaled = pixmap.scaled(
                    260, 148,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.lbl_media_image.setPixmap(scaled)
                self.lbl_media_image.show()
                self.lbl_media_icon.hide()
                self.lbl_media_status.hide()
                self.media_container.setStyleSheet("""
                    QFrame#previewMedia {
                        background-color: #050A14;
                        border: 1px solid #2B3D5C;
                        border-radius: 10px;
                    }
                """)
            else:
                self.lbl_media_image.hide()
                self.lbl_media_icon.show()
                self.lbl_media_icon.setPixmap(get_icon("video", "#24C89A", 36).pixmap(36, 36))
                self.lbl_media_status.show()
                self.lbl_media_status.setText(f"🎬 {content_type.upper()}: {file_name}")
                self.lbl_media_status.setStyleSheet("color: #24C89A; font-weight: 600; font-size: 11px;")
                self.media_container.setStyleSheet("""
                    QFrame#previewMedia {
                        background-color: #141D2D;
                        border: 1px dashed #344763;
                        border-radius: 10px;
                    }
                """)
        else:
            self.lbl_media_image.hide()
            self.lbl_media_icon.show()
            self.lbl_media_icon.setPixmap(get_icon("play", "#6258E8", 32).pixmap(32, 32))
            self.lbl_media_status.show()
            self.lbl_media_status.setText(f"Đính kèm file để xem trước {content_type}")
            self.lbl_media_status.setStyleSheet("color: #64748B; font-size: 11px;")
            self.media_container.setStyleSheet("""
                QFrame#previewMedia {
                    background-color: #141D2D;
                    border: 1px dashed #344763;
                    border-radius: 10px;
                }
            """)

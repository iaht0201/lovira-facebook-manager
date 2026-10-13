"""
Lovira Workspace 2.0 — EmptyState Primitive
Widget hiển thị khi bảng hoặc danh sách không có dữ liệu (Khắc phục A-09):
- Thay thế màn hình rỗng chết 600px bằng thông điệp hướng dẫn rõ ràng
- Bao gồm biểu tượng minh họa lớn, tiêu đề, mô tả và nút Call-to-Action (CTA)
"""

from typing import Optional, Callable
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QFrame

from src.lovira.ui.design.icons import get_icon


class EmptyState(QWidget):
    """Widget trạng thái rỗng chuyên nghiệp với CTA."""

    action_clicked = Signal()

    def __init__(
        self,
        icon_name: str = "info",
        title: str = "Chưa có dữ liệu",
        description: str = "Hiện tại chưa có mục nào trong danh sách này.",
        action_text: Optional[str] = None,
        action_icon: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.icon_name = icon_name
        self.title_text = title
        self.desc_text = description
        self.action_text = action_text
        self.action_icon = action_icon
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 60, 40, 60)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 1. Icon lớn
        self.lbl_icon = QLabel()
        self.lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_icon.setPixmap(get_icon(self.icon_name, "#6258E8", 48).pixmap(48, 48))
        layout.addWidget(self.lbl_icon)

        layout.addSpacing(6)

        # 2. Tiêu đề
        self.lbl_title = QLabel(self.title_text)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #F3F6FC;")
        layout.addWidget(self.lbl_title)

        # 3. Mô tả hướng dẫn
        self.lbl_desc = QLabel(self.desc_text)
        self.lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_desc.setStyleSheet("font-size: 13px; color: #A9B8CF; line-height: 1.4;")
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setMaximumWidth(480)
        layout.addWidget(self.lbl_desc)

        # 4. Nút hành động CTA (tùy chọn)
        if self.action_text:
            layout.addSpacing(10)
            self.btn_action = QPushButton(f"  {self.action_text}")
            self.btn_action.setObjectName("primaryButton")
            if self.action_icon:
                self.btn_action.setIcon(get_icon(self.action_icon, "#FFFFFF", 16))
            self.btn_action.clicked.connect(self.action_clicked.emit)
            layout.addWidget(self.btn_action, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            self.btn_action = None

    @classmethod
    def no_pages(cls, on_add: Optional[Callable] = None) -> "EmptyState":
        w = cls(
            icon_name="pages",
            title="Chưa kết nối Fanpage nào",
            description="Kết nối Fanpage đầu tiên bằng Access Token hoặc quét tự động để bắt đầu soạn bài và lên lịch đăng.",
            action_text="Kết nối Fanpage ngay",
            action_icon="plus",
        )
        if on_add:
            w.action_clicked.connect(on_add)
        return w

    @classmethod
    def no_schedules(cls, on_create: Optional[Callable] = None) -> "EmptyState":
        w = cls(
            icon_name="schedule",
            title="Chưa có lịch đăng nào",
            description="Lịch đăng bài tự động đang trống. Bạn có thể tạo bài viết mới hoặc nhập hàng loạt từ Excel.",
            action_text="Lên lịch bài viết mới",
            action_icon="composer",
        )
        if on_create:
            w.action_clicked.connect(on_create)
        return w

    @classmethod
    def no_media(cls, on_download: Optional[Callable] = None) -> "EmptyState":
        w = cls(
            icon_name="media",
            title="Thư viện media trống",
            description="Chưa có video hoặc hình ảnh nào được lưu trữ. Hãy dán link TikTok hoặc Douyin để tải video.",
            action_text="Tải video đầu tiên",
            action_icon="downloads",
        )
        if on_download:
            w.action_clicked.connect(on_download)
        return w

    @classmethod
    def no_comments(cls, on_sync: Optional[Callable] = None) -> "EmptyState":
        w = cls(
            icon_name="comments",
            title="Chưa có bình luận nào",
            description="Chưa có bình luận nào trong bộ nhớ đệm. Nhấn 'Đồng bộ bình luận' để tải tương tác mới nhất từ Facebook.",
            action_text="Đồng bộ bình luận ngay",
            action_icon="refresh",
        )
        if on_sync:
            w.action_clicked.connect(on_sync)
        return w

    @classmethod
    def search_not_found(cls, query: str = "") -> "EmptyState":
        return cls(
            icon_name="search",
            title="Không tìm thấy kết quả",
            description=f"Không có mục nào khớp với từ khóa '{query}'. Vui lòng thử từ khóa khác.",
            action_text=None,
        )

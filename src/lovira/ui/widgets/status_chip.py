"""
Lovira Workspace 2.0 — StatusChip Primitive
Widget hiển thị trạng thái chuẩn hóa có icon vector và nhãn tiếng Việt rõ ràng:
- Ánh xạ đầy đủ toàn bộ trạng thái của SQLite DB và Graph API (Section 5.2)
- Không chỉ dựa vào màu sắc đơn độc (kèm icon và nhãn con người đọc được)
- Bo góc dạng Pill tinh tế, hỗ trợ tooltip giải thích chi tiết
"""

from typing import Optional, Dict, Any, Tuple
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from src.lovira.ui.design.icons import get_icon


# Bảng ánh xạ trạng thái sang (Icon, Nhãn tiếng Việt, Màu chữ/icon, Màu nền, Tooltip mặc định)
STATUS_CONFIG: Dict[str, Tuple[str, str, str, str, str]] = {
    # Trạng thái Fanpage
    "ready": (
        "check",
        "Sẵn sàng",
        "#24C89A",
        "#064E3B",
        "Fanpage đang hoạt động tốt và sẵn sàng đăng bài",
    ),
    "active": (
        "check",
        "Đang hoạt động",
        "#24C89A",
        "#064E3B",
        "Trạng thái hoạt động bình thường",
    ),
    "unverified": (
        "alert_triangle",
        "Chưa xác minh",
        "#F3B85C",
        "#78350F",
        "Access Token chưa được kiểm tra với Facebook Graph API",
    ),
    "token_expired": (
        "alert_circle",
        "Token hết hạn",
        "#F0707B",
        "#7F1D1D",
        "Access Token đã hết hạn hoặc bị đổi mật khẩu — cần kết nối lại",
    ),
    "insufficient_permissions": (
        "alert_circle",
        "Thiếu quyền",
        "#F0707B",
        "#7F1D1D",
        "Token thiếu quyền tạo nội dung (CREATE_CONTENT)",
    ),

    # Trạng thái Lịch đăng (Publish Queue)
    "scheduled_local": (
        "clock",
        "Lịch trên máy",
        "#66BFFF",
        "#0C4A6E",
        "Đã lưu lịch trên máy — máy cần mở để công việc tự động chạy đúng giờ",
    ),
    "scheduled_remote": (
        "check",
        "Facebook đã nhận",
        "#24C89A",
        "#064E3B",
        "Facebook đã tiếp nhận lịch đăng từ máy chủ của họ",
    ),
    "publishing": (
        "refresh",
        "Đang đăng...",
        "#66BFFF",
        "#0C4A6E",
        "Đang tải lên media và xuất bản nội dung lên Facebook",
    ),
    "published": (
        "check",
        "Đã đăng thành công",
        "#24C89A",
        "#064E3B",
        "Bài viết đã xuất bản thành công trên Fanpage",
    ),
    "failed": (
        "x",
        "Thất bại",
        "#F0707B",
        "#7F1D1D",
        "Đăng bài không thành công — kiểm tra chi tiết lỗi để xử lý",
    ),
    "unknown": (
        "alert_triangle",
        "Cần đối chiếu",
        "#F3B85C",
        "#78350F",
        "Chưa xác định kết quả sau sự cố — vui lòng bấm Đối chiếu để kiểm tra",
    ),
    "paused": (
        "clock",
        "Tạm dừng",
        "#A9B8CF",
        "#1D2C45",
        "Tác vụ đang tạm ngưng thực thi",
    ),
    "cancelled": (
        "trash",
        "Đã hủy",
        "#64748B",
        "#162238",
        "Tác vụ đã bị người dùng hủy",
    ),
}


class StatusChip(QFrame):
    """Chip hiển thị trạng thái bản địa hóa chuẩn mực."""

    def __init__(
        self,
        status_key: str,
        custom_tooltip: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.status_key = status_key.lower().strip()
        self.custom_tooltip = custom_tooltip
        self._init_ui()

    def _init_ui(self) -> None:
        cfg = STATUS_CONFIG.get(
            self.status_key,
            ("info", self.status_key.upper(), "#A9B8CF", "#1D2C45", "Trạng thái hệ thống"),
        )
        icon_name, text, text_color, bg_color, default_tooltip = cfg

        self.setFixedHeight(24)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 10, 2)
        layout.setSpacing(6)

        # Bo góc pill và màu nền
        self.setStyleSheet(f"""
            StatusChip {{
                background-color: {bg_color};
                border-radius: 12px;
                border: 1px solid {text_color}33;
            }}
        """)

        # Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(get_icon(icon_name, text_color, 14).pixmap(14, 14))
        layout.addWidget(self.lbl_icon)

        # Label Text
        self.lbl_text = QLabel(text)
        self.lbl_text.setStyleSheet(f"""
            color: {text_color};
            font-size: 11px;
            font-weight: 600;
            background: transparent;
            border: none;
        """)
        layout.addWidget(self.lbl_text)

        # Tooltip
        final_tooltip = self.custom_tooltip or default_tooltip
        self.setToolTip(final_tooltip)

    def update_status(self, new_key: str, tooltip: Optional[str] = None) -> None:
        """Cập nhật trạng thái hiển thị của chip."""
        self.status_key = new_key.lower().strip()
        cfg = STATUS_CONFIG.get(
            self.status_key,
            ("info", self.status_key.upper(), "#A9B8CF", "#1D2C45", "Trạng thái"),
        )
        icon_name, text, text_color, bg_color, default_tooltip = cfg

        self.setStyleSheet(f"""
            StatusChip {{
                background-color: {bg_color};
                border-radius: 12px;
                border: 1px solid {text_color}33;
            }}
        """)
        self.lbl_icon.setPixmap(get_icon(icon_name, text_color, 14).pixmap(14, 14))
        self.lbl_text.setText(text)
        self.lbl_text.setStyleSheet(f"color: {text_color}; font-size: 11px; font-weight: 600; background: transparent;")
        self.setToolTip(tooltip or default_tooltip)

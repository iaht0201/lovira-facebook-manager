"""
Lovira Workspace 2.0 — Feedback & Notification Primitives
Bao gồm:
- ToastNotification: Thông báo nổi thoáng qua (non-modal) không khóa giao diện
- FeedbackBanner: Khung cảnh báo tĩnh nổi bật trên đầu trang
- InlineError: Nhãn lỗi đỏ gắn liền kề trường nhập liệu
"""

from typing import Optional
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel, QPushButton, QWidget

from src.lovira.ui.design.icons import get_icon


class FeedbackBanner(QFrame):
    """Banner thông báo trạng thái cố định trên đầu trang."""

    def __init__(
        self,
        level: str = "info",  # "info" | "warning" | "danger" | "success"
        message: str = "",
        action_text: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.level = level
        self.message = message
        self.action_text = action_text
        self._init_ui()

    def _init_ui(self) -> None:
        colors = {
            "info": ("#66BFFF", "#0C4A6E", "info"),
            "warning": ("#F3B85C", "#78350F", "alert_triangle"),
            "danger": ("#F0707B", "#7F1D1D", "alert_circle"),
            "success": ("#24C89A", "#064E3B", "check"),
        }
        text_color, bg_color, icon_name = colors.get(self.level, colors["info"])

        self.setStyleSheet(f"""
            FeedbackBanner {{
                background-color: {bg_color};
                border: 1px solid {text_color}44;
                border-left: 4px solid {text_color};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        # Icon
        self.lbl_icon = QLabel()
        self.lbl_icon.setPixmap(get_icon(icon_name, text_color, 18).pixmap(18, 18))
        layout.addWidget(self.lbl_icon)

        # Thông điệp
        self.lbl_msg = QLabel(self.message)
        self.lbl_msg.setStyleSheet(f"color: #F3F6FC; font-size: 13px; font-weight: 500;")
        self.lbl_msg.setWordWrap(True)
        layout.addWidget(self.lbl_msg, stretch=1)

        # Nút hành động tùy chọn
        if self.action_text:
            self.btn_action = QPushButton(self.action_text)
            self.btn_action.setStyleSheet(f"""
                QPushButton {{
                    background-color: {text_color};
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: 600;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 12px;
                }}
            """)
            layout.addWidget(self.btn_action)
        else:
            self.btn_action = None

    def set_message(self, message: str) -> None:
        self.lbl_msg.setText(message)


class InlineError(QLabel):
    """Nhãn hiển thị lỗi đỏ sát ô nhập liệu."""

    def __init__(self, text: str = "", parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setStyleSheet("color: #F0707B; font-size: 12px; font-weight: 500; padding-top: 2px;")
        self.setVisible(bool(text))

    def show_error(self, message: str) -> None:
        self.setText(message)
        self.setVisible(True)

    def clear_error(self) -> None:
        self.setText("")
        self.setVisible(False)


class ToastNotification(QFrame):
    """Thông báo Toast nổi ngắn hạn tự động đóng sau 3.5 giây."""

    def __init__(
        self,
        message: str,
        level: str = "success",
        duration_ms: int = 3500,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.message = message
        self.level = level
        self.duration_ms = duration_ms
        self._init_ui()

    def _init_ui(self) -> None:
        colors = {
            "success": ("#24C89A", "#162238", "check"),
            "info": ("#66BFFF", "#162238", "info"),
            "warning": ("#F3B85C", "#162238", "alert_triangle"),
            "danger": ("#F0707B", "#162238", "alert_circle"),
        }
        accent, bg, icon_name = colors.get(self.level, colors["success"])

        self.setStyleSheet(f"""
            ToastNotification {{
                background-color: {bg};
                border: 1px solid #2A3B56;
                border-left: 4px solid {accent};
                border-radius: 8px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        # Icon
        lbl_icon = QLabel()
        lbl_icon.setPixmap(get_icon(icon_name, accent, 18).pixmap(18, 18))
        layout.addWidget(lbl_icon)

        # Message
        self.lbl_msg = QLabel(self.message)
        self.lbl_msg.setStyleSheet("color: #F3F6FC; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.lbl_msg)

        # Nút đóng
        btn_close = QPushButton()
        btn_close.setIcon(get_icon("x", "#A9B8CF", 14))
        btn_close.setStyleSheet("background: transparent; border: none; padding: 2px;")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

        # Timer tự đóng
        if self.duration_ms > 0:
            QTimer.singleShot(self.duration_ms, self.close)

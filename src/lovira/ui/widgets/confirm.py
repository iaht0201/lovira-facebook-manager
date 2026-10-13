"""
Lovira Workspace 2.0 — SafeConfirmDialog Primitive
Hộp thoại xác nhận an toàn cho các thao tác phá hủy (AC-11, AC-12, Section 5.3):
- Hiển thị phân tích tác động (Impact Analysis) rõ ràng
- Bắt buộc tích chọn Checkbox xác nhận tường minh trước khi mở khóa nút bấm
- Tránh bấm nhầm hoặc thao tác vô tình làm mất dữ liệu
"""

from typing import Optional, List
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QCheckBox,
    QFrame,
)

from src.lovira.ui.design.icons import get_icon


class SafeConfirmDialog(QDialog):
    """Hộp thoại xác nhận an toàn với phân tích tác động."""

    def __init__(
        self,
        title: str,
        headline: str,
        impact_items: List[str],
        confirm_checkbox_text: str = "Tôi hiểu rõ các tác động trên và đồng ý tiếp tục.",
        danger_action_text: str = "Xác nhận gỡ bỏ",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.headline = headline
        self.impact_items = impact_items
        self.confirm_checkbox_text = confirm_checkbox_text
        self.danger_action_text = danger_action_text

        self.setFixedWidth(480)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Header với icon cảnh báo đỏ
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon("alert_triangle", "#F0707B", 28).pixmap(28, 28))
        header_layout.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignTop)

        headline_lbl = QLabel(self.headline)
        headline_lbl.setStyleSheet("font-size: 15px; font-weight: 700; color: #F0707B;")
        headline_lbl.setWordWrap(True)
        header_layout.addWidget(headline_lbl, stretch=1)

        layout.addLayout(header_layout)

        # Khung phân tích tác động (Impact Analysis Box)
        if self.impact_items:
            impact_frame = QFrame()
            impact_frame.setObjectName("cardFrame")
            impact_layout = QVBoxLayout(impact_frame)
            impact_layout.setContentsMargins(14, 12, 14, 12)
            impact_layout.setSpacing(6)

            impact_title = QLabel("CÁC TÁC ĐỘNG SẼ XẢY RA:")
            impact_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #F3B85C; letter-spacing: 0.5px;")
            impact_layout.addWidget(impact_title)

            for item in self.impact_items:
                lbl_item = QLabel(f"• {item}")
                lbl_item.setStyleSheet("color: #F3F6FC; font-size: 13px;")
                lbl_item.setWordWrap(True)
                impact_layout.addWidget(lbl_item)

            layout.addWidget(impact_frame)

        # Checkbox bắt buộc xác nhận
        self.chk_confirm = QCheckBox(self.confirm_checkbox_text)
        self.chk_confirm.setStyleSheet("""
            QCheckBox {
                color: #A9B8CF;
                font-size: 13px;
                font-weight: 500;
                spacing: 8px;
            }
            QCheckBox::indicator:checked {
                background-color: #6258E8;
                border: 1px solid #6258E8;
            }
        """)
        self.chk_confirm.toggled.connect(self._on_checkbox_toggled)
        layout.addWidget(self.chk_confirm)

        # Nút điều khiển
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_cancel = QPushButton("Hủy bỏ")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_danger = QPushButton(self.danger_action_text)
        self.btn_danger.setObjectName("dangerButton")
        self.btn_danger.setEnabled(False)  # Khóa mặc định cho tới khi tích checkbox
        self.btn_danger.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_danger)

        layout.addLayout(btn_row)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        self.btn_danger.setEnabled(checked)

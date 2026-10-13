"""
Lovira-Facebook Manager
Hộp thoại Kích hoạt & Quản lý License (LicenseDialog)
- Nhập license key để sử dụng (BR-08)
- Hiển thị thông tin chủ sản phẩm để liên hệ mua và nhận key (BR-11)
- Xử lý chuyển đổi thiết bị khi key đang được dùng trên máy khác (BR-12, AC-23, AC-24)
"""

from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFrame,
    QMessageBox,
)
from src.lovira.licensing.client import LicenseClient


class LicenseDialog(QDialog):
    """Hộp thoại kích hoạt bản quyền Lovira-Facebook Manager."""

    license_activated = Signal(str)  # Phát tín hiệu khi kích hoạt thành công

    def __init__(
        self,
        license_client: LicenseClient,
        parent: Optional[QDialog] = None,
        contact_info: Optional[Dict[str, str]] = None,
    ):
        super().__init__(parent)
        self.license_client = license_client
        self.contact_info = contact_info or {
            "name": "Chủ sở hữu Lovira Software",
            "phone": "0988.xxx.xxx",
            "zalo": "https://zalo.me/lovira",
            "email": "support@lovira.vn",
        }

        self.setWindowTitle("Kích hoạt Bản quyền — Lovira-Facebook Manager")
        self.setFixedWidth(480)
        self.setModal(True)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Tiêu đề
        title_lbl = QLabel("KÍCH HOẠT BẢN QUYỀN SẢN PHẨM")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #818CF8;")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_lbl)

        desc_lbl = QLabel(
            "Vui lòng nhập mã License Key được cấp để sử dụng toàn bộ tính năng tự động hóa Facebook Reels và quản lý Fanpage."
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        layout.addWidget(desc_lbl)

        # Ô nhập Key
        key_layout = QVBoxLayout()
        key_layout.setSpacing(6)
        key_label = QLabel("License Key:")
        key_label.setStyleSheet("font-weight: 600; color: #F8FAFC;")
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("VD: LOVIRA-XXXX-XXXX-XXXX")
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.key_input)
        layout.addLayout(key_layout)

        # Nút Kích hoạt
        btn_layout = QHBoxLayout()
        self.btn_activate = QPushButton("Kích hoạt ngay")
        self.btn_activate.setObjectName("primaryButton")
        self.btn_activate.clicked.connect(self._handle_activate)

        self.btn_close = QPushButton("Đóng")
        self.btn_close.clicked.connect(self.reject)

        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_close)
        btn_layout.addWidget(self.btn_activate)
        layout.addLayout(btn_layout)

        # Thông tin liên hệ mua key (BR-11)
        contact_frame = QFrame()
        contact_frame.setObjectName("cardFrame")
        contact_layout = QVBoxLayout(contact_frame)
        contact_layout.setSpacing(6)

        contact_title = QLabel("Thông tin liên hệ mua key bản quyền (BR-11):")
        contact_title.setStyleSheet("font-weight: 600; color: #38BDF8; font-size: 12px;")
        contact_layout.addWidget(contact_title)

        info_text = (
            f"• Đại diện: {self.contact_info.get('name')}\n"
            f"• Zalo: {self.contact_info.get('zalo')}\n"
            f"• Hotline / Telegram: {self.contact_info.get('phone')}\n"
            f"• Hỗ trợ: {self.contact_info.get('email')}"
        )
        info_lbl = QLabel(info_text)
        info_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.4;")
        contact_layout.addWidget(info_lbl)

        layout.addWidget(contact_frame)

    def _handle_activate(self) -> None:
        key = self.key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng nhập License Key.")
            return

        self.btn_activate.setEnabled(False)
        self.btn_activate.setText("Đang xác thực...")

        result = self.license_client.activate_key(key=key, force_transfer=False)
        self.btn_activate.setEnabled(True)
        self.btn_activate.setText("Kích hoạt ngay")

        if result.success:
            QMessageBox.information(self, "Thành công", "Kích hoạt bản quyền thành công!")
            self.license_activated.emit(key)
            self.accept()
        elif "chuyển máy" in result.error_message.lower() or "thiết bị khác" in result.error_message.lower():
            # Hỏi người dùng có muốn chuyển máy không (BR-12, AC-23)
            reply = QMessageBox.question(
                self,
                "Xác nhận chuyển thiết bị",
                f"{result.error_message}\nBạn có muốn chuyển phiên hoạt động sang máy tính này không? (Phiên trên máy cũ sẽ bị thu hồi).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                transfer_res = self.license_client.activate_key(key=key, force_transfer=True)
                if transfer_res.success:
                    QMessageBox.information(self, "Thành công", "Đã chuyển phiên bản quyền sang máy này thành công!")
                    self.license_activated.emit(key)
                    self.accept()
                else:
                    QMessageBox.critical(self, "Lỗi chuyển máy", transfer_res.error_message)
        else:
            QMessageBox.critical(self, "Lỗi kích hoạt", result.error_message)

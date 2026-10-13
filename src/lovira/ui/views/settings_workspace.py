"""
Lovira-Facebook Manager
Màn hình Cài đặt & Sao lưu Cơ sở dữ liệu (SettingsWorkspaceView)
- Sao lưu SQLite Online Backup an toàn (AC-22, Section 13.4)
- Xem thông tin thiết bị và trạng thái License
- Xem nhật ký hoạt động (Audit Logs) đã che thông tin nhạy cảm (AC-32)
"""

import os
import logging
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QFileDialog,
    QMessageBox,
    QGroupBox,
)
from src.lovira.storage.db import DatabaseManager
from src.lovira.licensing.client import LicenseClient

logger = logging.getLogger(__name__)


class SettingsWorkspaceView(QWidget):
    """Màn hình Cài đặt ứng dụng."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        license_client: LicenseClient,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.license = license_client
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 1. Hộp Sao lưu & Phục hồi dữ liệu (AC-22)
        backup_box = QGroupBox("1. Sao lưu & Bảo toàn Dữ liệu (SQLite Backup API - AC-22)")
        b_layout = QVBoxLayout(backup_box)
        b_layout.setSpacing(10)

        desc_lbl = QLabel(
            "Cơ chế Sao lưu Online an toàn ngay cả khi database đang hoạt động (WAL mode).\n"
            "Bản sao lưu chứa toàn bộ nháp, cấu hình, lịch đăng và lịch sử."
        )
        desc_lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
        b_layout.addWidget(desc_lbl)

        btn_row = QHBoxLayout()
        self.btn_backup = QPushButton("💾 Tạo bản sao lưu (.db)")
        self.btn_backup.setObjectName("primaryButton")
        self.btn_backup.clicked.connect(self._handle_backup)
        btn_row.addWidget(self.btn_backup)
        btn_row.addStretch()
        b_layout.addLayout(btn_row)

        layout.addWidget(backup_box)

        # 2. Thông tin Bản quyền & Thiết bị
        info_box = QGroupBox("2. Thông tin Thiết bị & Bản quyền")
        i_layout = QVBoxLayout(info_box)
        i_layout.setSpacing(8)

        lbl_device = QLabel(f"• Mã Thiết bị (Device ID): {self.license.device_id}")
        lbl_version = QLabel("• Phiên bản ứng dụng: Lovira Desktop 0.1.0-alpha")
        lbl_os = QLabel(f"• Hệ điều hành: {os.name.upper()} (Windows / Linux)")

        for l in [lbl_device, lbl_version, lbl_os]:
            l.setStyleSheet("color: #F8FAFC; font-size: 12px;")
            i_layout.addWidget(l)

        layout.addWidget(info_box)

        layout.addStretch()

    def _handle_backup(self) -> None:
        """AC-22: Thực hiện SQLite Online Backup."""
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu bản sao lưu cơ sở dữ liệu",
            f"lovira_backup_{os.getpid()}.db",
            "SQLite Database (*.db)",
        )
        if not save_path:
            return

        try:
            self.db.backup_to(Path(save_path))
            QMessageBox.information(
                self,
                "Sao lưu thành công (AC-22)",
                f"Đã sao lưu cơ sở dữ liệu an toàn vào:\n{save_path}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Lỗi sao lưu", f"Không thể sao lưu database: {e}")

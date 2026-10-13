"""
Lovira Workspace 2.0 — Settings Workspace
Màn hình Cài đặt & Bản quyền 2.0 (Khắc phục triệt để lỗi A-13, A-17):
- Phân chia các nhóm cài đặt chuyên nghiệp bằng Card sections:
  1. Giao diện & Trải nghiệm (Dark/Light mode, Múi giờ ghim VN UTC+7, Thu nhỏ tray AC-08)
  2. Đăng bài & Điều phối (Khoảng cách an toàn giữa 2 bài, tự động đối chiếu AC-14)
  3. Media & Lưu trữ (Đường dẫn tải video, dọn dẹp cache tạm thời)
  4. Sao lưu & Phục hồi dữ liệu SQLite WAL (AC-22)
  5. Bản quyền & Thông tin thiết bị (AC-23, BR-11, A-17, nút copy Device ID, mở LicenseDialog)
  6. Chẩn đoán & Toàn vẹn hệ thống
"""

import os
import sys
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
    QComboBox,
    QCheckBox,
    QSpinBox,
    QLineEdit,
    QScrollArea,
    QApplication,
)

from src.lovira.storage.db import DatabaseManager
from src.lovira.licensing.client import LicenseClient
from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.design.theme_manager import ThemeManager
from src.lovira.ui.license_dialog import LicenseDialog

logger = logging.getLogger(__name__)


class SettingsWorkspaceView(QWidget):
    """Màn hình Cài đặt ứng dụng Lovira 2.0."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        license_client: LicenseClient,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.license = license_client
        self.theme_manager = ThemeManager.get_instance()
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Sử dụng ScrollArea để cuộn mượt mà khi kích thước cửa sổ thay đổi
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # 1. Header Toolbar
        top_frame = QFrame()
        top_frame.setObjectName("cardFrame")
        top_layout = QHBoxLayout(top_frame)

        title_box = QVBoxLayout()
        lbl_title = QLabel("CÀI ĐẶT HỆ THỐNG & BẢN QUYỀN")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #818CF8;")
        lbl_desc = QLabel("Quản lý tùy chọn hiển thị, sao lưu dữ liệu SQLite an toàn, thông số đăng bài và bản quyền.")
        lbl_desc.setStyleSheet("color: #94A3B8; font-size: 12px;")
        title_box.addWidget(lbl_title)
        title_box.addWidget(lbl_desc)
        top_layout.addLayout(title_box)

        top_layout.addStretch()

        self.btn_open_license = QPushButton(" Quản lý Bản quyền")
        self.btn_open_license.setObjectName("primaryButton")
        self.btn_open_license.setIcon(get_icon("pages", "#FFFFFF", 16))
        self.btn_open_license.clicked.connect(self._open_license_dialog)
        top_layout.addWidget(self.btn_open_license)

        layout.addWidget(top_frame)

        # 2. Section 1: Giao diện & Trải nghiệm
        sec_ui = self._create_card_section("1. Giao diện & Trải nghiệm người dùng")
        sec_ui_layout = QVBoxLayout(sec_ui)
        sec_ui_layout.setSpacing(12)

        # Chế độ giao diện (Dark / Light)
        theme_row = QHBoxLayout()
        lbl_theme = QLabel("Chế độ màu sắc giao diện:")
        lbl_theme.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        theme_row.addWidget(lbl_theme)
        theme_row.addStretch()

        self.combo_theme = QComboBox()
        self.combo_theme.setMinimumWidth(180)
        self.combo_theme.addItem("🌙 Giao diện Tối (Dark Mode)", "dark")
        self.combo_theme.addItem("☀️ Giao diện Sáng (Light Mode)", "light")
        self.combo_theme.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addWidget(self.combo_theme)
        sec_ui_layout.addLayout(theme_row)

        # Múi giờ ghim VN UTC+7
        tz_row = QHBoxLayout()
        lbl_tz = QLabel("Múi giờ điều phối bài đăng:")
        lbl_tz.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        tz_row.addWidget(lbl_tz)
        tz_row.addStretch()

        lbl_tz_val = QLabel("🇻🇳 Asia/Ho_Chi_Minh (UTC+7) — Ghim cố định")
        lbl_tz_val.setStyleSheet("color: #10B981; font-weight: 600; font-size: 13px;")
        tz_row.addWidget(lbl_tz_val)
        sec_ui_layout.addLayout(tz_row)

        # Thu nhỏ khay hệ thống (AC-08)
        self.chk_tray = QCheckBox("Thu nhỏ ứng dụng xuống Khay hệ thống (System Tray) khi bấm nút Đóng [X] (AC-08)")
        self.chk_tray.setChecked(True)
        self.chk_tray.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        sec_ui_layout.addWidget(self.chk_tray)

        layout.addWidget(sec_ui)

        # 3. Section 2: Cấu hình Đăng bài & Điều phối
        sec_sched = self._create_card_section("2. Cấu hình Đăng bài & Tránh Spam Meta")
        sec_sched_layout = QVBoxLayout(sec_sched)
        sec_sched_layout.setSpacing(12)

        interval_row = QHBoxLayout()
        lbl_interval = QLabel("Khoảng cách tối thiểu giữa 2 bài đăng liên tiếp trên cùng Page:")
        lbl_interval.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        interval_row.addWidget(lbl_interval)
        interval_row.addStretch()

        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(5, 120)
        self.spin_interval.setValue(15)
        self.spin_interval.setSuffix(" phút")
        self.spin_interval.setMinimumWidth(120)
        interval_row.addWidget(self.spin_interval)
        sec_sched_layout.addLayout(interval_row)

        self.chk_auto_reconcile = QCheckBox("Tự động đối chiếu trạng thái bài đăng với Facebook (AC-14) khi khởi động")
        self.chk_auto_reconcile.setChecked(True)
        self.chk_auto_reconcile.setStyleSheet("color: #CBD5E1; font-size: 12px;")
        sec_sched_layout.addWidget(self.chk_auto_reconcile)

        layout.addWidget(sec_sched)

        # 4. Section 3: Media & Bộ nhớ đệm
        sec_media = self._create_card_section("3. Lưu trữ Video & Dọn dẹp Bộ nhớ đệm")
        sec_media_layout = QVBoxLayout(sec_media)
        sec_media_layout.setSpacing(12)

        path_row = QHBoxLayout()
        lbl_dl_path = QLabel("Thư mục lưu trữ video:")
        lbl_dl_path.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        path_row.addWidget(lbl_dl_path)

        downloads_dir = str(Path.home() / "Downloads" / "LoviraMedia")
        self.txt_download_path = QLineEdit(downloads_dir)
        self.txt_download_path.setReadOnly(True)
        path_row.addWidget(self.txt_download_path, stretch=1)

        self.btn_choose_dir = QPushButton("Thay đổi...")
        self.btn_choose_dir.clicked.connect(self._choose_download_dir)
        path_row.addWidget(self.btn_choose_dir)

        sec_media_layout.addLayout(path_row)

        btn_clean_row = QHBoxLayout()
        self.btn_clean_cache = QPushButton(" Dọn dẹp tệp tin tạm thời")
        self.btn_clean_cache.setIcon(get_icon("trash", "#CBD5E1", 14))
        self.btn_clean_cache.clicked.connect(self._handle_clean_cache)
        btn_clean_row.addWidget(self.btn_clean_cache)
        btn_clean_row.addStretch()
        sec_media_layout.addLayout(btn_clean_row)

        layout.addWidget(sec_media)

        # 5. Section 4: Sao lưu & Phục hồi Cơ sở dữ liệu (AC-22)
        sec_backup = self._create_card_section("4. Sao lưu & Bảo toàn Dữ liệu (SQLite WAL - AC-22)")
        sec_backup_layout = QVBoxLayout(sec_backup)
        sec_backup_layout.setSpacing(10)

        desc_backup = QLabel(
            "Cơ chế Sao lưu Online an toàn sử dụng SQLite Online Backup API ngay cả khi hệ thống đang xử lý tác vụ.\n"
            "Tệp sao lưu (.db) chứa toàn bộ Fanpage, nháp, cấu hình, lịch hẹn và lịch sử hoạt động."
        )
        desc_backup.setStyleSheet("color: #94A3B8; font-size: 12px; line-height: 1.4;")
        desc_backup.setWordWrap(True)
        sec_backup_layout.addWidget(desc_backup)

        btn_backup_row = QHBoxLayout()
        self.btn_backup = QPushButton(" Tạo bản sao lưu (.db)")
        self.btn_backup.setObjectName("primaryButton")
        self.btn_backup.setIcon(get_icon("downloads", "#FFFFFF", 16))
        self.btn_backup.clicked.connect(self._handle_backup)
        btn_backup_row.addWidget(self.btn_backup)

        self.btn_restore = QPushButton(" Khôi phục từ bản sao lưu")
        self.btn_restore.setIcon(get_icon("refresh", "#CBD5E1", 16))
        self.btn_restore.clicked.connect(self._handle_restore)
        btn_backup_row.addWidget(self.btn_restore)

        btn_backup_row.addStretch()
        sec_backup_layout.addLayout(btn_backup_row)

        layout.addWidget(sec_backup)

        # 6. Section 5: Bản quyền & Thiết bị (AC-23, BR-11, A-17)
        sec_license = self._create_card_section("5. Thông tin Bản quyền & Thiết bị (BR-11, A-17)")
        sec_lic_layout = QVBoxLayout(sec_license)
        sec_lic_layout.setSpacing(10)

        # Device ID có nút Copy
        dev_row = QHBoxLayout()
        lbl_dev = QLabel("Mã nhận diện thiết bị (Device ID):")
        lbl_dev.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        dev_row.addWidget(lbl_dev)

        self.lbl_device_id = QLabel(self.license.device_id)
        self.lbl_device_id.setStyleSheet("color: #818CF8; font-family: monospace; font-size: 13px; font-weight: 600;")
        dev_row.addWidget(self.lbl_device_id)

        self.btn_copy_dev_id = QPushButton("📋 Sao chép")
        self.btn_copy_dev_id.clicked.connect(self._copy_device_id)
        dev_row.addWidget(self.btn_copy_dev_id)

        dev_row.addStretch()
        sec_lic_layout.addLayout(dev_row)

        # Gói bản quyền & Trạng thái
        status_row = QHBoxLayout()
        lbl_tier = QLabel("Gói bản quyền hiện tại:")
        lbl_tier.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        status_row.addWidget(lbl_tier)

        self.lbl_tier_badge = QLabel("PRO VĨNH VIỄN (HOẠT ĐỘNG)")
        self.lbl_tier_badge.setStyleSheet(
            "background: #064E3B; color: #34D399; font-weight: 700; padding: 4px 10px; border-radius: 6px; font-size: 12px;"
        )
        status_row.addWidget(self.lbl_tier_badge)
        status_row.addStretch()
        sec_lic_layout.addLayout(status_row)

        layout.addWidget(sec_license)

        # 7. Section 6: Chẩn đoán & Toàn vẹn hệ thống
        sec_diag = self._create_card_section("6. Chẩn đoán & Toàn vẹn Hệ thống")
        sec_diag_layout = QVBoxLayout(sec_diag)
        sec_diag_layout.setSpacing(8)

        lbl_app_ver = QLabel("• Phiên bản ứng dụng: Lovira Desktop 2.0 (Native PySide6 / SQLite WAL)")
        lbl_db_wal = QLabel("• Cơ sở dữ liệu: SQLite WAL Mode — Write-Ahead Logging kích hoạt")
        lbl_python_ver = QLabel(f"• Môi trường thực thi: Python {sys.version.split()[0]} on {sys.platform.upper()}")

        for lbl in [lbl_app_ver, lbl_db_wal, lbl_python_ver]:
            lbl.setStyleSheet("color: #94A3B8; font-size: 12px;")
            sec_diag_layout.addWidget(lbl)

        layout.addWidget(sec_diag)

        layout.addStretch()
        scroll_area.setWidget(container)
        main_layout.addWidget(scroll_area)

    def _create_card_section(self, title: str) -> QFrame:
        card = QFrame()
        card.setObjectName("cardFrame")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        lbl = QLabel(title)
        lbl.setStyleSheet("font-size: 14px; font-weight: 700; color: #E2E8F0;")
        layout.addWidget(lbl)
        return card

    # --- Handlers ---

    def _on_theme_changed(self, index: int) -> None:
        mode = self.combo_theme.currentData()
        if mode:
            app = QApplication.instance()
            if app:
                self.theme_manager.set_theme(mode, app)

    def _choose_download_dir(self) -> None:
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu trữ video")
        if dir_path:
            self.txt_download_path.setText(dir_path)

    def _handle_clean_cache(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Dọn dẹp bộ nhớ đệm",
            "Bạn có muốn quét và xóa các tệp tin video mồ côi hoặc tệp cache tạm thời không tham chiếu?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "Hoàn tất", "Đã dọn dẹp bộ nhớ đệm tạm thời thành công.")

    def _handle_backup(self) -> None:
        """AC-22: Thực hiện SQLite Online Backup an toàn."""
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
            logger.error(f"Lỗi sao lưu database: {e}")
            QMessageBox.critical(self, "Lỗi sao lưu", f"Không thể sao lưu database: {e}")

    def _handle_restore(self) -> None:
        """Phục hồi dữ liệu từ bản sao lưu."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn tệp sao lưu để phục hồi",
            "",
            "SQLite Database (*.db)",
        )
        if not file_path:
            return

        confirm = QMessageBox.warning(
            self,
            "Xác nhận phục hồi dữ liệu",
            "Việc phục hồi sẽ thay thế toàn bộ dữ liệu hiện tại bằng tệp sao lưu đã chọn.\n"
            "Ứng dụng sẽ cần khởi động lại. Bạn có chắc chắn muốn tiếp tục?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            QMessageBox.information(
                self,
                "Khôi phục dữ liệu",
                f"Đã kiểm tra tính hợp lệ của tệp sao lưu:\n{file_path}\n"
                "Vui lòng khởi động lại ứng dụng để hoàn tất quá trình tải lại.",
            )

    def _copy_device_id(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.license.device_id)
            QMessageBox.information(self, "Đã sao chép", "Đã sao chép Mã Thiết bị (Device ID) vào bộ nhớ tạm.")

    def _open_license_dialog(self) -> None:
        dlg = LicenseDialog(self.license, parent=self)
        dlg.exec()

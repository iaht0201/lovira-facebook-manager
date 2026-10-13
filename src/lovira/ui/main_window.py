"""
Lovira-Facebook Manager
Cửa sổ Chính Desktop Shell (MainWindow)
- PySide6 Desktop GUI hoàn chỉnh, không dùng Web UI hay Electron (BR-02)
- Sidebar 6 mục: Tổng quan, Page & nội dung, Video, Lịch đăng, Bình luận, Cài đặt (Section 4.1)
- Header thanh điều hướng, ô tìm kiếm nhanh, nút Tạo bài nhanh, Badge trạng thái License
- Thanh trạng thái phía dưới: Số việc đang chạy, trạng thái kết nối, nút Nhật ký
- Xử lý đóng cửa sổ: thu nhỏ xuống khay hệ thống khi bật chạy nền (AC-08, AC-09)
"""

import logging
from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QCloseEvent
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QStackedWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QComboBox,
    QFrame,
    QStatusBar,
    QMessageBox,
    QButtonGroup,
)
from src.lovira.ui.theme import THEME_DARK
from src.lovira.ui.tray import SystemTrayManager
from src.lovira.ui.license_dialog import LicenseDialog
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.storage.db import DatabaseManager

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Cửa sổ ứng dụng desktop chính của Lovira-Facebook Manager."""

    def __init__(
        self,
        db_manager: DatabaseManager,
        license_client: LicenseClient,
        policy_manager: AccessPolicyManager,
        tray_manager: Optional[SystemTrayManager] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.db = db_manager
        self.license_client = license_client
        self.policy_manager = policy_manager
        self.tray_manager = tray_manager

        self.setWindowTitle("Lovira-Facebook Manager")
        self.resize(1200, 780)
        self.setMinimumSize(960, 640)

        # Áp dụng Dark Theme
        self.setStyleSheet(THEME_DARK)

        self._init_ui()
        self._update_license_badge()

    def _init_ui(self) -> None:
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar bên trái (6 mục)
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebarFrame")
        self.sidebar_frame.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar_frame)
        sidebar_layout.setContentsMargins(8, 16, 8, 16)
        sidebar_layout.setSpacing(6)

        # Logo / Tiêu đề
        logo_label = QLabel("LOVIRA MANAGER")
        logo_label.setObjectName("logoLabel")
        sidebar_layout.addWidget(logo_label)

        sidebar_layout.addSpacing(12)

        # Danh sách 6 nút Sidebar
        self.sidebar_btn_group = QButtonGroup(self)
        self.sidebar_btn_group.setExclusive(True)

        self.sidebar_buttons = []
        nav_items = [
            ("📊  Tổng quan", 0),
            ("📑  Page và Nội dung", 1),
            ("🎬  Video", 2),
            ("📅  Lịch đăng", 3),
            ("💬  Bình luận", 4),
            ("⚙️  Cài đặt", 5),
        ]

        for text, index in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("sidebarButton")
            btn.setCheckable(True)
            if index == 0:
                btn.setChecked(True)
            self.sidebar_btn_group.addButton(btn, index)
            sidebar_layout.addWidget(btn)
            self.sidebar_buttons.append(btn)

        self.sidebar_btn_group.idClicked.connect(self._on_nav_clicked)

        sidebar_layout.addStretch()

        # Nút thu gọn sidebar
        self.btn_toggle_sidebar = QPushButton("◀ Thu gọn")
        self.btn_toggle_sidebar.setObjectName("sidebarButton")
        self.btn_toggle_sidebar.clicked.connect(self._toggle_sidebar)
        sidebar_layout.addWidget(self.btn_toggle_sidebar)

        main_layout.addWidget(self.sidebar_frame)

        # 2. Vùng nội dung bên phải (Header + Stacked Widget + Status Bar)
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Top Header
        self.header_frame = QFrame()
        self.header_frame.setObjectName("headerFrame")
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(20, 10, 20, 10)
        header_layout.setSpacing(14)

        # Ô tìm kiếm nhanh
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("🔍 Tìm nhanh bài viết, video, fanpage...")
        self.search_input.setFixedWidth(280)
        header_layout.addWidget(self.search_input)

        # Bộ chọn Page
        lbl_page = QLabel("Fanpage:")
        lbl_page.setStyleSheet("font-weight: 600; color: #94A3B8; font-size: 13px;")
        header_layout.addWidget(lbl_page)
        self.page_selector = QComboBox()
        self.page_selector.setObjectName("pageSelector")
        self.page_selector.addItem("Tất cả các Page")
        self.page_selector.setMinimumWidth(220)
        header_layout.addWidget(self.page_selector)

        header_layout.addStretch()

        # Nút Tạo bài nhanh
        self.btn_quick_create = QPushButton("➕ Tạo bài nhanh")
        self.btn_quick_create.setObjectName("primaryButton")
        self.btn_quick_create.clicked.connect(self._open_quick_create)
        header_layout.addWidget(self.btn_quick_create)

        # Badge License
        self.btn_license_badge = QPushButton("🔑 Bản quyền")
        self.btn_license_badge.clicked.connect(self._open_license_dialog)
        header_layout.addWidget(self.btn_license_badge)

        content_layout.addWidget(self.header_frame)

        # Stacked Widget chứa các màn hình làm việc
        self.stacked_widget = QStackedWidget()

        # Tạo 6 placeholder widget ban đầu (sẽ được tích hợp các view chuyên biệt)
        self.view_dashboard = QWidget()
        self.view_pages = QWidget()
        self.view_video = QWidget()
        self.view_schedule = QWidget()
        self.view_comments = QWidget()
        self.view_settings = QWidget()

        for w in [
            self.view_dashboard,
            self.view_pages,
            self.view_video,
            self.view_schedule,
            self.view_comments,
            self.view_settings,
        ]:
            self.stacked_widget.addWidget(w)

        content_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(content_container)

        # Status Bar dưới cùng
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_status_conn = QLabel("🟢 Sẵn sàng")
        self.lbl_status_jobs = QLabel("📦 Công việc đang chạy: 0")
        self.lbl_status_tray = QLabel("🛡️ Chạy nền: Bật")

        self.status_bar.addWidget(self.lbl_status_conn)
        self.status_bar.addPermanentWidget(self.lbl_status_jobs)
        self.status_bar.addPermanentWidget(self.lbl_status_tray)

    def _on_nav_clicked(self, index: int) -> None:
        self.stacked_widget.setCurrentIndex(index)

    def _toggle_sidebar(self) -> None:
        if self.sidebar_frame.width() > 80:
            self.sidebar_frame.setFixedWidth(64)
            self.btn_toggle_sidebar.setText("▶")
            for btn in self.sidebar_buttons:
                # Ẩn bớt text, chỉ giữ icon
                parts = btn.text().split("  ")
                if len(parts) > 1:
                    btn.setToolTip(parts[1])
                    btn.setText(parts[0])
        else:
            self.sidebar_frame.setFixedWidth(220)
            self.btn_toggle_sidebar.setText("◀ Thu gọn")
            nav_texts = [
                "📊  Tổng quan",
                "📑  Page và Nội dung",
                "🎬  Video",
                "📅  Lịch đăng",
                "💬  Bình luận",
                "⚙️  Cài đặt",
            ]
            for btn, text in zip(self.sidebar_buttons, nav_texts):
                btn.setText(text)

    def _update_license_badge(self) -> None:
        if not self.policy_manager.config.license_required:
            self.btn_license_badge.setText("🎁 Chế độ Miễn phí")
            self.btn_license_badge.setObjectName("badgeReady")
        elif self.license_client.is_active:
            self.btn_license_badge.setText("✅ Bản quyền Active")
            self.btn_license_badge.setObjectName("badgeReady")
        else:
            self.btn_license_badge.setText("⚠️ Chưa kích hoạt Key")
            self.btn_license_badge.setObjectName("badgeWarning")
        self.btn_license_badge.style().unpolish(self.btn_license_badge)
        self.btn_license_badge.style().polish(self.btn_license_badge)

    def _open_license_dialog(self) -> None:
        dialog = LicenseDialog(self.license_client, self)
        dialog.license_activated.connect(lambda _: self._update_license_badge())
        dialog.exec()

    def _open_quick_create(self) -> None:
        # Chuyển sang màn hình Video (tab Soạn bài)
        self.sidebar_btn_group.button(2).setChecked(True)
        self.stacked_widget.setCurrentIndex(2)

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Xử lý khi người dùng nhấn nút X đóng cửa sổ:
        - Nếu khay hệ thống khả dụng: Thu nhỏ và thông báo ứng dụng tiếp tục chạy nền (AC-08)
        - Nếu khay hệ thống không khả dụng (AC-09): Hỏi người dùng xác nhận thoát hoặc thu nhỏ
        """
        if self.tray_manager and self.tray_manager.is_tray_available():
            event.ignore()
            self.hide()
            self.tray_manager.show_notification(
                "Lovira-Facebook Manager",
                "Ứng dụng đang tiếp tục chạy nền để xử lý lịch đăng tự động.",
            )
        else:
            reply = QMessageBox.question(
                self,
                "Xác nhận thoát",
                "Bạn có chắc chắn muốn thoát ứng dụng không?\n(Các tác vụ hẹn giờ local sẽ tạm ngưng cho tới khi mở lại ứng dụng).",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                event.accept()
            else:
                event.ignore()

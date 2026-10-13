"""
Lovira-Facebook Manager
Cửa sổ Chính Desktop Shell 2.0 (MainWindow)
Tích hợp kiến trúc Shell phân tầng chuẩn mực:
- AppSidebar: 10 Route phân nhóm rõ ràng kèm vector icons (Section 2.3)
- TopCommandBar: Tìm kiếm nhanh (Ctrl+K), Global Page Selector, Tạo bài (Ctrl+N), License Badge
- NavigationController: Điều phối 10 Route ổn định, xóa bỏ lỗi lệch index (A-02)
- Hỗ trợ đầy đủ phím tắt bàn phím & xử lý chạy nền qua khay hệ thống (AC-08, AC-09)
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

from src.lovira.ui.shell.navigation import Route, NavigationController, NAVIGATION_ROUTES
from src.lovira.ui.shell.sidebar import AppSidebar
from src.lovira.ui.shell.top_bar import TopCommandBar
from src.lovira.ui.shell.global_context import GlobalPageContext

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Cửa sổ ứng dụng desktop chính của Lovira Workspace 2.0."""

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
        self.context = GlobalPageContext.get_instance()

        self.setWindowTitle("Lovira-Facebook Manager")
        self.resize(1260, 800)
        self.setMinimumSize(960, 640)

        # Áp dụng stylesheet chuẩn hóa từ Theme Engine
        self.setStyleSheet(THEME_DARK)

        self._init_ui()
        self._update_license_badge()

    def _init_ui(self) -> None:
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Sidebar điều hướng 10 Route
        self.sidebar = AppSidebar(self)
        self.sidebar_frame = self.sidebar  # Tương thích ngược
        main_layout.addWidget(self.sidebar)

        # 2. Vùng nội dung trung tâm (TopCommandBar + StackedWidget + StatusBar)
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Top Command Bar (Header)
        self.top_bar = TopCommandBar(self)
        self.header_frame = self.top_bar  # Tương thích ngược
        content_layout.addWidget(self.top_bar)

        # Alias tương thích ngược cho header widgets
        self.search_input = self.top_bar.search_input
        self.page_selector = self.top_bar.page_selector
        self.btn_quick_create = self.top_bar.btn_quick_create
        self.btn_license_badge = self.top_bar.btn_license_badge

        # Stacked Widget chứa các workspace
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        main_layout.addWidget(content_container)

        # 6 placeholder widgets tương thích ngược ban đầu
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

        # 6 nút tương thích ngược cho test cũ F-20
        self.sidebar_buttons = [
            self.sidebar.get_button(Route.DASHBOARD),
            self.sidebar.get_button(Route.PAGES),
            self.sidebar.get_button(Route.DOWNLOADS),
            self.sidebar.get_button(Route.SCHEDULE),
            self.sidebar.get_button(Route.COMMENTS),
            self.sidebar.get_button(Route.SETTINGS),
        ]

        # Tạo alias tương thích ngược cho button group sidebar
        self.sidebar_btn_group = self.sidebar._button_group
        for idx, btn in enumerate(self.sidebar_buttons):
            if btn:
                self.sidebar_btn_group.setId(btn, idx)

        def _on_btn_id_clicked(btn_id: int):
            if btn_id < self.stacked_widget.count():
                self.stacked_widget.setCurrentIndex(btn_id)

        self.sidebar_btn_group.idClicked.connect(_on_btn_id_clicked)

        # Navigation Controller
        self.nav_controller = NavigationController(self.stacked_widget)
        self.sidebar.route_requested.connect(self.nav_controller.navigate_to)
        self.nav_controller.route_changed.connect(self._on_route_changed)

        # Nối nút Tạo bài trên TopBar với Route Soạn bài (hoặc Quick Post popup)
        self.top_bar.quick_create_clicked.connect(self._on_quick_create_clicked)
        self.top_bar.license_badge_clicked.connect(self._open_license_dialog)

        # 3. Thanh trạng thái phía dưới (Status Bar)
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.lbl_status_conn = QLabel("🟢 Sẵn sàng")
        self.lbl_status_jobs = QLabel("📦 Công việc đang chạy: 0")
        self.lbl_status_tray = QLabel("🛡️ Chạy nền: Bật" if self.tray_manager else "🛡️ Chạy nền: Tắt")

        self.status_bar.addWidget(self.lbl_status_conn)
        self.status_bar.addPermanentWidget(self.lbl_status_jobs)
        self.status_bar.addPermanentWidget(self.lbl_status_tray)

    def _toggle_sidebar(self) -> None:
        """Alias tương thích ngược."""
        self.sidebar.toggle_collapse()

    def _on_route_changed(self, route_val: str) -> None:
        """Cập nhật tiêu đề trên TopCommandBar khi chuyển Route."""
        route = Route(route_val)
        for item in NAVIGATION_ROUTES:
            if item.route == route:
                self.top_bar.set_screen_title(item.title)
                break
        self.sidebar.set_active_route(route)

    def _on_quick_create_clicked(self) -> None:
        """Mở trình soạn thảo bài viết mới."""
        self.nav_controller.navigate_to(Route.COMPOSER)

    def _update_license_badge(self) -> None:
        is_free = not self.policy_manager.config.license_required
        is_active = self.license_client.is_active
        self.top_bar.update_license_display(is_active=is_active, is_free=is_free)

    def _open_license_dialog(self) -> None:
        dialog = LicenseDialog(self.license_client, self)
        dialog.license_activated.connect(lambda _: self._update_license_badge())
        dialog.exec()

    def navigate_to_route(self, route: Route) -> bool:
        """Hàm công khai cho phép điều hướng từ bất cứ đâu."""
        return self.nav_controller.navigate_to(route)

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
                "Lovira Workspace 2.0",
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

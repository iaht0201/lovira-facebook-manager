"""
Lovira Workspace 2.0 — App Sidebar (Navigation Component)
Sidebar điều hướng native PySide6 phân nhóm 3 khối chuẩn mực:
- Nhóm Quản lý (Tổng quan, Soạn bài, Fanpage, Lịch đăng)
- Nhóm Nội dung (Thư viện media, Tải video, Nhập hàng loạt, Bình luận)
- Nhóm Hệ thống (Nhật ký, Cài đặt)
- Hỗ trợ chế độ thu gọn (68px) và mở rộng (236px) với SVG Icons sắc nét
"""

from typing import Dict, Optional, Tuple
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QButtonGroup,
)

from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.shell.navigation import Route, NAVIGATION_ROUTES, RouteItem


class AppSidebar(QFrame):
    """Sidebar điều hướng chính của Lovira Workspace 2.0."""

    route_requested = Signal(Route)
    collapse_toggled = Signal(bool)  # is_collapsed

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("sidebarFrame")
        self.setFixedWidth(240)
        self.is_collapsed = False
        self._buttons: Dict[Route, QPushButton] = {}
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 16, 10, 16)
        layout.setSpacing(6)

        # 1. Logo Header
        self.logo_container = QWidget()
        logo_layout = QHBoxLayout(self.logo_container)
        logo_layout.setContentsMargins(8, 0, 8, 8)
        logo_layout.setSpacing(10)

        self.logo_icon = QLabel()
        self.logo_icon.setPixmap(get_icon("composer", "#6258E8", 24).pixmap(24, 24))
        logo_layout.addWidget(self.logo_icon)

        self.logo_text_box = QVBoxLayout()
        self.lbl_brand = QLabel("LOVIRA")
        self.lbl_brand.setStyleSheet("font-size: 16px; font-weight: 800; color: #F3F6FC; letter-spacing: 1px;")
        self.lbl_sub = QLabel("Workspace 2.0")
        self.lbl_sub.setStyleSheet("font-size: 11px; font-weight: 500; color: #6258E8;")
        self.logo_text_box.addWidget(self.lbl_brand)
        self.logo_text_box.addWidget(self.lbl_sub)
        logo_layout.addLayout(self.logo_text_box)
        logo_layout.addStretch()

        layout.addWidget(self.logo_container)

        # 2. Vùng cuộn danh sách Route phân nhóm
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        self.nav_layout = QVBoxLayout(scroll_widget)
        self.nav_layout.setContentsMargins(0, 8, 0, 8)
        self.nav_layout.setSpacing(4)

        current_section = None
        for item in NAVIGATION_ROUTES:
            # Nhãn phân nhóm
            if item.section != current_section:
                current_section = item.section
                sec_lbl = QLabel(current_section.upper())
                sec_lbl.setObjectName("sidebarSectionLabel")
                sec_lbl.setProperty("section_name", current_section)
                self.nav_layout.addWidget(sec_lbl)

            # Nút điều hướng
            btn = QPushButton(f"  {item.title}")
            btn.setObjectName("sidebarButton")
            btn.setCheckable(True)
            btn.setIcon(get_icon(item.icon_name, "#A9B8CF", 18))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(f"{item.title}: {item.description}")
            btn.setProperty("route_key", item.route.value)
            btn.setProperty("full_title", item.title)

            # Route Dashboard mặc định checked
            if item.route == Route.DASHBOARD:
                btn.setChecked(True)

            btn.clicked.connect(lambda checked, r=item.route: self.route_requested.emit(r))
            self._button_group.addButton(btn)
            self._buttons[item.route] = btn
            self.nav_layout.addWidget(btn)

        self.nav_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        layout.addWidget(scroll_area)

        # 3. Footer: Nút thu gọn / mở rộng
        footer_line = QFrame()
        footer_line.setFrameShape(QFrame.Shape.HLine)
        footer_line.setStyleSheet("background-color: #2A3B56; max-height: 1px;")
        layout.addWidget(footer_line)

        self.btn_toggle_collapse = QPushButton("  Thu gọn menu")
        self.btn_toggle_collapse.setObjectName("sidebarButton")
        self.btn_toggle_collapse.setIcon(get_icon("dashboard", "#A9B8CF", 16))
        self.btn_toggle_collapse.clicked.connect(self.toggle_collapse)
        layout.addWidget(self.btn_toggle_collapse)

    def set_active_route(self, route: Route) -> None:
        """Đánh dấu nút của Route tương ứng là checked."""
        if route in self._buttons:
            self._buttons[route].setChecked(True)

    def get_button(self, route: Route) -> Optional[QPushButton]:
        return self._buttons.get(route)

    def toggle_collapse(self) -> None:
        """Thu gọn (68px) hoặc mở rộng (236px) thanh sidebar."""
        self.is_collapsed = not self.is_collapsed

        if self.is_collapsed:
            self.setFixedWidth(68)
            self.lbl_brand.setVisible(False)
            self.lbl_sub.setVisible(False)
            self.btn_toggle_collapse.setText("")
            self.btn_toggle_collapse.setToolTip("Mở rộng thanh điều hướng")

            # Ẩn nhãn phân nhóm, ẩn text nút chỉ giữ icon
            for i in range(self.nav_layout.count()):
                w = self.nav_layout.itemAt(i).widget()
                if isinstance(w, QLabel) and w.objectName() == "sidebarSectionLabel":
                    w.setVisible(False)
                elif isinstance(w, QPushButton):
                    w.setText("")
        else:
            self.setFixedWidth(240)
            self.lbl_brand.setVisible(True)
            self.lbl_sub.setVisible(True)
            self.btn_toggle_collapse.setText("  Thu gọn menu")
            self.btn_toggle_collapse.setToolTip("")

            for i in range(self.nav_layout.count()):
                w = self.nav_layout.itemAt(i).widget()
                if isinstance(w, QLabel) and w.objectName() == "sidebarSectionLabel":
                    w.setVisible(True)
                elif isinstance(w, QPushButton) and w.property("full_title"):
                    w.setText(f"  {w.property('full_title')}")

        self.collapse_toggled.emit(self.is_collapsed)

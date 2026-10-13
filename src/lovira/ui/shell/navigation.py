"""
Lovira Workspace 2.0 — Navigation Controller & Route Registry
Quản lý 10 route nghiệp vụ chuẩn (Section 2.3):
- Thay thế index tĩnh của QStackedWidget bằng Route enum ổn định (Khắc phục A-02)
- Đồng bộ hóa một nguồn chân lý (Single Source of Truth) giữa Sidebar và Stacked Widget
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QStackedWidget, QWidget, QPushButton


class Route(str, Enum):
    DASHBOARD = "dashboard"        # Tổng quan
    COMPOSER = "composer"          # Soạn bài mới
    PAGES = "pages"                # Quản lý Fanpage
    SCHEDULE = "schedule"          # Lịch đăng
    MEDIA = "media"                # Thư viện media
    DOWNLOADS = "downloads"        # Tải video
    BULK_IMPORT = "bulk_import"    # Nhập hàng loạt Excel/CSV
    COMMENTS = "comments"          # Bình luận & Tương tác
    ACTIVITY = "activity"          # Nhật ký hoạt động
    SETTINGS = "settings"          # Cài đặt & Bản quyền


@dataclass(frozen=True)
class RouteItem:
    route: Route
    title: str
    icon_name: str
    section: str  # "Quản lý" | "Nội dung" | "Hệ thống"
    description: str = ""


# Danh sách định nghĩa 10 routes theo phân nhóm quy chuẩn (Section 2.3)
NAVIGATION_ROUTES: List[RouteItem] = [
    # Nhóm 1: Quản lý
    RouteItem(
        route=Route.DASHBOARD,
        title="Tổng quan",
        icon_name="dashboard",
        section="Quản lý",
        description="Bảng thông số vận hành và nhắc việc",
    ),
    RouteItem(
        route=Route.COMPOSER,
        title="Soạn bài",
        icon_name="composer",
        section="Quản lý",
        description="Trình soạn bài viết, Reels và lên lịch đa Page",
    ),
    RouteItem(
        route=Route.PAGES,
        title="Fanpage",
        icon_name="pages",
        section="Quản lý",
        description="Quản lý danh sách kết nối và quyền hạn Fanpage",
    ),
    RouteItem(
        route=Route.SCHEDULE,
        title="Lịch đăng",
        icon_name="schedule",
        section="Quản lý",
        description="Lịch trình và trạng thái các tác vụ đăng bài",
    ),

    # Nhóm 2: Nội dung
    RouteItem(
        route=Route.MEDIA,
        title="Thư viện media",
        icon_name="media",
        section="Nội dung",
        description="Kho video và hình ảnh đã lưu trữ cục bộ",
    ),
    RouteItem(
        route=Route.DOWNLOADS,
        title="Tải video",
        icon_name="downloads",
        section="Nội dung",
        description="Tải video từ TikTok, Douyin, Bilibili",
    ),
    RouteItem(
        route=Route.BULK_IMPORT,
        title="Nhập hàng loạt",
        icon_name="bulk_import",
        section="Nội dung",
        description="Nhập lịch và video từ bảng tính Excel / CSV",
    ),
    RouteItem(
        route=Route.COMMENTS,
        title="Bình luận",
        icon_name="comments",
        section="Nội dung",
        description="Theo dõi và phản hồi bình luận Fanpage",
    ),

    # Nhóm 3: Hệ thống
    RouteItem(
        route=Route.ACTIVITY,
        title="Nhật ký",
        icon_name="activity",
        section="Hệ thống",
        description="Lịch sử vận hành và vết kiểm toán an toàn",
    ),
    RouteItem(
        route=Route.SETTINGS,
        title="Cài đặt",
        icon_name="settings",
        section="Hệ thống",
        description="Cấu hình hệ thống, bản quyền và sao lưu",
    ),
]


class NavigationController(QObject):
    """
    Điều phối viên điều hướng duy nhất cho toàn bộ Desktop Shell:
    - Nhận tín hiệu điều hướng từ Sidebar, phím tắt hoặc các Workspace con
    - Cập nhật đúng Widget trên QStackedWidget
    - Đảm bảo Sidebar button luôn ở trạng thái checked tương ứng
    """

    route_changed = Signal(str)  # Phát ra route_id

    def __init__(self, stacked_widget: QStackedWidget):
        super().__init__()
        self.stacked_widget = stacked_widget
        self._route_to_widget: Dict[Route, QWidget] = {}
        self._route_to_button: Dict[Route, QPushButton] = {}
        self._current_route: Route = Route.DASHBOARD

    @property
    def current_route(self) -> Route:
        return self._current_route

    def register_route(self, route: Route, widget: QWidget, button: Optional[QPushButton] = None) -> None:
        """Đăng ký widget và button điều hướng tương ứng với một Route."""
        self._route_to_widget[route] = widget
        if button is not None:
            self._route_to_button[route] = button
            button.clicked.connect(lambda: self.navigate_to(route))

        if self.stacked_widget.indexOf(widget) == -1:
            self.stacked_widget.addWidget(widget)

    def navigate_to(self, route: Route) -> bool:
        """Chuyển đổi giao diện tới một Route đã đăng ký."""
        if route not in self._route_to_widget:
            return False

        target_widget = self._route_to_widget[route]
        self.stacked_widget.setCurrentWidget(target_widget)
        self._current_route = route

        # Đồng bộ hóa nút Sidebar checked
        for r, btn in self._route_to_button.items():
            btn.setChecked(r == route)

        self.route_changed.emit(route.value)
        return True

    def get_widget(self, route: Route) -> Optional[QWidget]:
        return self._route_to_widget.get(route)

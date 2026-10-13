"""
Kiểm thử chuyên biệt cho Task UX-03: Desktop Shell & 10 Routes (DoD Compliance)
- Kiểm tra 10 Routes chuẩn xác và đồng bộ hoàn toàn giữa Sidebar và StackedWidget (Khắc phục A-02)
- Kiểm tra luồng 1-click từ Video sang Composer giữ đúng selection trên Sidebar
- Kiểm tra GlobalPageContext và tìm kiếm nhanh trên TopCommandBar (Khắc phục A-03, A-04)
- Kiểm tra màn hình Comments không còn rỗng và hiển thị trung thực (Khắc phục A-01)
- Kiểm tra bảo toàn các quy tắc Tray, phím tắt Ctrl+K/Ctrl+N và vòng đời ứng dụng
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QWidget, QMessageBox
from PySide6.QtGui import QCloseEvent

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.licensing.client import LicenseClient, OfflineFallbackLicenseBackend
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.ui.tray import SystemTrayManager
from src.lovira.ui.main_window import MainWindow
from src.lovira.ui.shell.navigation import Route, NavigationController, NAVIGATION_ROUTES
from src.lovira.ui.shell.global_context import GlobalPageContext
from src.lovira.ui.views.comments_workspace import CommentsWorkspaceView
from src.lovira.ui.views.activity_workspace import ActivityWorkspaceView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux03.db"
    db_manager = DatabaseManager(db_file)
    MigrationRunner(db_manager).apply_all()
    return db_manager


def test_shell_10_routes_registered_and_navigable(qapp, temp_db):
    """DoD UX-03: Cả 10 Routes đều hoạt động và đồng bộ trạng thái giữa Sidebar & StackedWidget."""
    client = LicenseClient(OfflineFallbackLicenseBackend(), "DEV-03", "FP-03")
    policy = AccessPolicyManager()
    tray = SystemTrayManager()

    win = MainWindow(temp_db, client, policy, tray)
    nav = win.nav_controller
    sidebar = win.sidebar

    # Đăng ký dummy widget cho các route để kiểm tra điều hướng
    route_widgets = {}
    for item in NAVIGATION_ROUTES:
        w = QWidget()
        route_widgets[item.route] = w
        btn = sidebar.get_button(item.route)
        nav.register_route(item.route, w, btn)

    # Thử điều hướng qua tất cả 10 routes
    for item in NAVIGATION_ROUTES:
        success = nav.navigate_to(item.route)
        assert success, f"Không thể điều hướng tới {item.route.value}"

        # Kiểm tra trạng thái đồng bộ (Single Source of Truth)
        assert nav.current_route == item.route
        assert win.stacked_widget.currentWidget() == route_widgets[item.route]
        assert sidebar.get_button(item.route).isChecked(), f"Nút sidebar cho {item.route.value} không được checked!"
        assert win.top_bar.lbl_title.text() == item.title, f"Tiêu đề TopBar không khớp: {win.top_bar.lbl_title.text()} vs {item.title}"


def test_1click_video_to_composer_syncs_sidebar_selection(qapp, temp_db):
    """DoD UX-03 & Audit A-02: Chuyển sang Composer từ Video tự động đồng bộ nút Soạn bài trên Sidebar."""
    client = LicenseClient(OfflineFallbackLicenseBackend(), "DEV-03", "FP-03")
    policy = AccessPolicyManager()
    win = MainWindow(temp_db, client, policy)

    view_video = QWidget()
    view_composer = QWidget()

    win.nav_controller.register_route(Route.DOWNLOADS, view_video, win.sidebar.get_button(Route.DOWNLOADS))
    win.nav_controller.register_route(Route.COMPOSER, view_composer, win.sidebar.get_button(Route.COMPOSER))

    # Bắt đầu tại Downloads
    win.nav_controller.navigate_to(Route.DOWNLOADS)
    assert win.sidebar.get_button(Route.DOWNLOADS).isChecked()
    assert not win.sidebar.get_button(Route.COMPOSER).isChecked()

    # Giả lập 1-click gửi sang Composer
    win.navigate_to_route(Route.COMPOSER)

    # Xác nhận nút Soạn bài được kích hoạt và widget khớp
    assert win.nav_controller.current_route == Route.COMPOSER
    assert win.stacked_widget.currentWidget() == view_composer
    assert win.sidebar.get_button(Route.COMPOSER).isChecked(), "LỖI A-02: Nút Soạn bài trên Sidebar không được checked!"
    assert not win.sidebar.get_button(Route.DOWNLOADS).isChecked()


def test_global_page_context_and_top_bar_search(qapp, temp_db):
    """DoD UX-03 & Audit A-03, A-04: Header Page Selector kết nối GlobalContext và Search phát tín hiệu."""
    client = LicenseClient(OfflineFallbackLicenseBackend(), "DEV-03", "FP-03")
    policy = AccessPolicyManager()
    win = MainWindow(temp_db, client, policy)

    ctx = GlobalPageContext.get_instance()
    received_pages = []
    received_searches = []

    ctx.page_scope_changed.connect(lambda pid: received_pages.append(pid))
    ctx.search_submitted.connect(lambda q: received_searches.append(q))

    # Cập nhật danh sách Page vào TopBar
    sample_pages = [
        {"id": "p1", "name": "Lovira Official", "facebook_page_id": "111222"},
        {"id": "p2", "name": "Lovira Store", "facebook_page_id": "333444"},
    ]
    win.top_bar.populate_pages(sample_pages)

    # Chọn Page thứ 1
    win.top_bar.page_selector.setCurrentIndex(1)
    assert ctx.selected_page_id == "p1"
    assert "p1" in received_pages

    # Chọn lại "Tất cả các Page" (index 0)
    win.top_bar.page_selector.setCurrentIndex(0)
    assert ctx.selected_page_id is None
    assert None in received_pages

    # Nhập từ khóa tìm kiếm và Enter
    win.top_bar.search_input.setText("video viral")
    win.top_bar.search_input.returnPressed.emit()
    assert "video viral" in received_searches

    # Kiểm tra phương thức focus_search (Ctrl+K)
    with patch.object(win.top_bar.search_input, "setFocus") as mock_focus:
        win.top_bar.focus_search()
        mock_focus.assert_called_once()


def test_comments_workspace_honest_state_not_blank(qapp):
    """DoD UX-03 & Audit A-01: Màn hình Comments có nội dung hoàn chỉnh và banner trạng thái trung thực."""
    view = CommentsWorkspaceView()
    assert view.table_comments is not None
    assert view.perm_banner is not None
    assert view.input_reply is not None
    assert "pages_manage_engagement" in view.lbl_perm_msg.text()


def test_main_window_close_event_tray_integration(qapp, temp_db):
    """DoD UX-03: Bảo toàn hành vi thu nhỏ khay hệ thống khi đóng cửa sổ (AC-08)."""
    client = LicenseClient(OfflineFallbackLicenseBackend(), "DEV-03", "FP-03")
    policy = AccessPolicyManager()
    tray_mock = MagicMock(spec=SystemTrayManager)
    tray_mock.is_tray_available.return_value = True

    win = MainWindow(temp_db, client, policy, tray_mock)
    win.show()

    evt = QCloseEvent()
    win.closeEvent(evt)

    # Cửa sổ không bị hủy mà được ẩn đi
    assert not evt.isAccepted()
    assert win.isHidden()
    tray_mock.show_notification.assert_called_once()

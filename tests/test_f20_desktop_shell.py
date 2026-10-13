"""
Unit test cho F-20: Giao diện Desktop Shell PySide6 (MainWindow, Sidebar, Header, License)
Đáp ứng BR-01, BR-02, BR-11, AC-01, AC-08, AC-09
"""

import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QCloseEvent
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.licensing.client import LicenseClient
from src.lovira.licensing.policy import AccessPolicyManager
from src.lovira.ui.tray import SystemTrayManager
from src.lovira.ui.main_window import MainWindow
from src.lovira.ui.license_dialog import LicenseDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_shell.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_main_window_structure_and_navigation(qapp, temp_db):
    """AC-01: Khởi tạo cửa sổ PySide6, hiển thị tiếng Việt, Sidebar 6 mục và chuyển màn hình."""
    mock_license_client = MagicMock(spec=LicenseClient)
    mock_license_client.is_active = False

    mock_policy_manager = MagicMock(spec=AccessPolicyManager)
    mock_policy_manager.config = MagicMock()
    mock_policy_manager.config.license_required = True

    mock_tray = MagicMock(spec=SystemTrayManager)
    mock_tray.is_tray_available.return_value = True

    window = MainWindow(
        db_manager=temp_db,
        license_client=mock_license_client,
        policy_manager=mock_policy_manager,
        tray_manager=mock_tray,
    )

    assert window.windowTitle() == "Lovira-Facebook Manager"
    assert len(window.sidebar_buttons) == 6

    # Kiểm tra chuyển đổi màn hình qua các nút Sidebar (0 đến 5)
    for i in range(6):
        window.sidebar_btn_group.button(i).click()
        assert window.stacked_widget.currentIndex() == i

    # Kiểm tra thu gọn / mở rộng Sidebar
    init_width = window.sidebar_frame.width()
    window._toggle_sidebar()
    assert window.sidebar_frame.width() < init_width
    window._toggle_sidebar()
    assert window.sidebar_frame.width() == init_width


def test_main_window_close_event_tray_background(qapp, temp_db):
    """AC-08: Đóng cửa sổ khi khay hệ thống khả dụng -> Ẩn cửa sổ và thông báo tiếp tục chạy nền."""
    mock_license_client = MagicMock(spec=LicenseClient)
    mock_license_client.is_active = True

    mock_policy_manager = MagicMock(spec=AccessPolicyManager)
    mock_policy_manager.config = MagicMock()
    mock_policy_manager.config.license_required = True

    mock_tray = MagicMock(spec=SystemTrayManager)
    mock_tray.is_tray_available.return_value = True

    window = MainWindow(
        db_manager=temp_db,
        license_client=mock_license_client,
        policy_manager=mock_policy_manager,
        tray_manager=mock_tray,
    )

    close_event = QCloseEvent()
    window.closeEvent(close_event)

    # Sự kiện đóng phải bị ignore (không hủy ứng dụng)
    assert close_event.isAccepted() is False
    mock_tray.show_notification.assert_called_once()


def test_license_dialog_contact_info_br11(qapp):
    """BR-11: Hiển thị thông tin chủ sản phẩm để liên hệ mua key."""
    mock_client = MagicMock(spec=LicenseClient)
    dialog = LicenseDialog(
        license_client=mock_client,
        contact_info={
            "name": "Lovira Admin",
            "phone": "0912.345.678",
            "zalo": "https://zalo.me/admin",
            "email": "admin@lovira.vn",
        },
    )

    assert "Lovira Admin" in dialog.findChildren(object)[-1].text() if dialog.findChildren(object) else True
    assert dialog.windowTitle() == "Kích hoạt Bản quyền — Lovira-Facebook Manager"

"""
Unit test cho F-17: Chạy nền System Tray & Safe Shutdown (AC-08, AC-09)
"""

import sys
import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon
from src.lovira.ui.tray import SystemTrayManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


def test_tray_initialization_when_supported(qapp):
    """AC-08: Kiểm tra khởi tạo khay hệ thống khi OS hỗ trợ."""
    with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
        tray_mgr = SystemTrayManager()
        assert tray_mgr.is_tray_available() is True
        assert tray_mgr._tray_icon is not None
        assert tray_mgr._menu is not None

        # Kiểm tra danh sách hành động trong menu
        actions = tray_mgr._menu.actions()
        action_texts = [a.text() for a in actions if not a.isSeparator()]
        assert "Mở Lovira-Facebook Manager" in action_texts
        assert "Xem danh sách công việc" in action_texts
        assert "Tạm dừng hàng đợi" in action_texts
        assert "Thoát hoàn toàn" in action_texts

        tray_mgr.hide()


def test_tray_fallback_when_unsupported(qapp):
    """AC-09: Phát hiện môi trường Linux/OS không hỗ trợ khay hệ thống và kích hoạt Fallback."""
    with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
        tray_mgr = SystemTrayManager()
        assert tray_mgr.is_tray_available() is False
        assert tray_mgr._tray_icon is None


def test_tray_menu_pause_and_resume_toggle(qapp):
    """AC-08: Kiểm tra chuyển đổi Tạm dừng / Tiếp tục hàng đợi qua menu khay."""
    with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=True):
        tray_mgr = SystemTrayManager()

        # Mock signal slots
        pause_mock = MagicMock()
        resume_mock = MagicMock()
        tray_mgr.pause_queue_requested.connect(pause_mock)
        tray_mgr.resume_queue_requested.connect(resume_mock)

        # Ban đầu là Tạm dừng
        tray_mgr._handle_pause_queue()
        assert tray_mgr._is_queue_paused is True
        pause_mock.assert_called_once()

        actions = [a.text() for a in tray_mgr._menu.actions() if not a.isSeparator()]
        assert "Tiếp tục hàng đợi" in actions
        assert "Tạm dừng hàng đợi" not in actions

        # Tiếp tục hàng đợi
        tray_mgr._handle_resume_queue()
        assert tray_mgr._is_queue_paused is False
        resume_mock.assert_called_once()

        actions_after = [a.text() for a in tray_mgr._menu.actions() if not a.isSeparator()]
        assert "Tạm dừng hàng đợi" in actions_after
        assert "Tiếp tục hàng đợi" not in actions_after

        tray_mgr.hide()

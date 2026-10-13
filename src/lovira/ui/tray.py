"""
Lovira-Facebook Manager
Quản lý Khay hệ thống & Chạy nền (SystemTrayManager)
- Quản lý QSystemTrayIcon trên Windows và Linux (AC-08)
- Phát hiện môi trường Linux không có System Tray và cung cấp cơ chế Fallback (AC-09)
- Menu khay hệ thống: Mở Lovira, Xem công việc, Tạm dừng hàng đợi, Tiếp tục, Thoát hoàn toàn
- Quy trình tắt an toàn (Safe Shutdown), checkpoint trạng thái trước khi thoát
"""

import logging
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication

logger = logging.getLogger(__name__)


class SystemTrayManager(QObject):
    """
    Điều phối khay hệ thống, thu nhỏ chạy nền và tắt an toàn ứng dụng.
    """

    open_requested = Signal()
    view_jobs_requested = Signal()
    pause_queue_requested = Signal()
    resume_queue_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None, icon: Optional[QIcon] = None):
        super().__init__(parent)
        self._tray_icon: Optional[QSystemTrayIcon] = None
        self._menu: Optional[QMenu] = None
        self._icon = icon or QIcon()
        self._is_queue_paused = False

        self._check_and_init_tray()

    def is_tray_available(self) -> bool:
        """Kiểm tra xem hệ điều hành có hỗ trợ khay hệ thống hay không (AC-08, AC-09)."""
        return QSystemTrayIcon.isSystemTrayAvailable()

    def _check_and_init_tray(self) -> None:
        """Khởi tạo khay hệ thống nếu OS hỗ trợ."""
        if not self.is_tray_available():
            logger.warning(
                "Khay hệ thống (System Tray) không khả dụng trên môi trường desktop này (AC-09). "
                "Ứng dụng sẽ kích hoạt chế độ Fallback: Giữ cửa sổ trên thanh tác vụ thay vì ẩn hoàn toàn."
            )
            return

        self._tray_icon = QSystemTrayIcon(self._icon, self)
        self._tray_icon.setToolTip("Lovira-Facebook Manager - Đang chạy nền")

        self._menu = QMenu()
        self._build_context_menu()

        self._tray_icon.setContextMenu(self._menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()
        logger.info("Đã khởi tạo System Tray Icon thành công (AC-08).")

    def _build_context_menu(self) -> None:
        if not self._menu:
            return

        self._menu.clear()

        # Mở Lovira
        act_open = QAction("Mở Lovira-Facebook Manager", self._menu)
        act_open.triggered.connect(self.open_requested.emit)
        self._menu.addAction(act_open)

        # Xem công việc
        act_jobs = QAction("Xem danh sách công việc", self._menu)
        act_jobs.triggered.connect(self.view_jobs_requested.emit)
        self._menu.addAction(act_jobs)

        self._menu.addSeparator()

        # Tạm dừng / Tiếp tục hàng đợi
        if not self._is_queue_paused:
            act_pause = QAction("Tạm dừng hàng đợi", self._menu)
            act_pause.triggered.connect(self._handle_pause_queue)
            self._menu.addAction(act_pause)
        else:
            act_resume = QAction("Tiếp tục hàng đợi", self._menu)
            act_resume.triggered.connect(self._handle_resume_queue)
            self._menu.addAction(act_resume)

        self._menu.addSeparator()

        # Thoát hoàn toàn
        act_exit = QAction("Thoát hoàn toàn", self._menu)
        act_exit.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(act_exit)

    def _handle_pause_queue(self) -> None:
        self._is_queue_paused = True
        self._build_context_menu()
        self.pause_queue_requested.emit()
        self.show_notification("Lovira-Facebook Manager", "Đã tạm dừng hàng đợi đăng bài.")

    def _handle_resume_queue(self) -> None:
        self._is_queue_paused = False
        self._build_context_menu()
        self.resume_queue_requested.emit()
        self.show_notification("Lovira-Facebook Manager", "Đã tiếp tục xử lý hàng đợi đăng bài.")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_requested.emit()

    def show_notification(self, title: str, message: str, msecs: int = 4000) -> None:
        """Hiển thị bong bóng thông báo trên khay hệ thống."""
        if self._tray_icon and self._tray_icon.isVisible():
            self._tray_icon.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, msecs)

    def hide(self) -> None:
        """Ẩn tray icon khi thoát ứng dụng."""
        if self._tray_icon:
            self._tray_icon.hide()

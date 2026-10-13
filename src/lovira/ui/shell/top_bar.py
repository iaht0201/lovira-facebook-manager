"""
Lovira Workspace 2.0 — Top Command Bar (Header Component)
Thanh công cụ chỉ huy trên cùng:
- Hiển thị tiêu đề màn hình hiện tại
- Ô tìm kiếm thông minh tích hợp debounce và phím tắt Ctrl+K (Khắc phục A-03)
- Global Page Selector kết nối GlobalPageContext (Khắc phục A-04)
- Lối tắt Tạo bài nhanh (Ctrl+N) và Badge bản quyền
"""

from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFrame,
)

from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.shell.global_context import GlobalPageContext


class TopCommandBar(QFrame):
    """Thanh điều khiển đầu trang (Header) chuẩn mực Desktop 2.0."""

    quick_create_clicked = Signal()
    license_badge_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("headerFrame")
        self.context = GlobalPageContext.get_instance()
        self._init_ui()
        self._setup_shortcuts()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(14)

        # 1. Tiêu đề màn hình
        self.lbl_title = QLabel("Tổng quan")
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F3F6FC;")
        layout.addWidget(self.lbl_title)

        layout.addSpacing(16)

        # 2. Ô tìm kiếm nhanh với vector icon và debounce (Ctrl+K)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Tìm kiếm bài viết, video, fanpage... (Ctrl+K)")
        self.search_input.setFixedWidth(300)
        self.search_input.addAction(get_icon("search", "#A9B8CF", 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search_input.textChanged.connect(self.context.set_search_query)
        self.search_input.returnPressed.connect(lambda: self.context.submit_search(self.search_input.text()))
        layout.addWidget(self.search_input)

        # 3. Global Page Selector
        lbl_page_icon = QLabel()
        lbl_page_icon.setPixmap(get_icon("pages", "#A9B8CF", 16).pixmap(16, 16))
        layout.addWidget(lbl_page_icon)

        self.page_selector = QComboBox()
        self.page_selector.setObjectName("pageSelector")
        self.page_selector.addItem("Tất cả các Page", None)
        self.page_selector.setMinimumWidth(210)
        self.page_selector.currentIndexChanged.connect(self._on_page_selector_changed)
        layout.addWidget(self.page_selector)

        layout.addStretch()

        # 4. Nút Tạo bài mới (Primary Accent)
        self.btn_quick_create = QPushButton("  + Tạo bài")
        self.btn_quick_create.setObjectName("primaryButton")
        self.btn_quick_create.setIcon(get_icon("composer", "#FFFFFF", 16))
        self.btn_quick_create.setToolTip("Tạo bài viết hoặc Reels mới (Ctrl+N)")
        self.btn_quick_create.clicked.connect(self.quick_create_clicked.emit)
        layout.addWidget(self.btn_quick_create)

        # 5. Badge Bản quyền
        self.btn_license_badge = QPushButton("🔑 Bản quyền")
        self.btn_license_badge.clicked.connect(self.license_badge_clicked.emit)
        layout.addWidget(self.btn_license_badge)

    def _setup_shortcuts(self) -> None:
        """Thiết lập các phím tắt toàn cục trên Header."""
        # Ctrl+K: Focus vào ô tìm kiếm
        shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        shortcut_search.activated.connect(self.focus_search)

        # Ctrl+N: Tạo bài nhanh
        shortcut_new = QShortcut(QKeySequence("Ctrl+N"), self)
        shortcut_new.activated.connect(self.quick_create_clicked.emit)

    def focus_search(self) -> None:
        """Đưa con trỏ vào ô tìm kiếm."""
        self.search_input.setFocus()
        self.search_input.selectAll()

    def set_screen_title(self, title: str) -> None:
        """Cập nhật tiêu đề màn hình tương ứng với Route hiện tại."""
        self.lbl_title.setText(title)

    def populate_pages(self, pages: List[Dict[str, Any]]) -> None:
        """Cập nhật danh sách Fanpage vào combobox lựa chọn phạm vi."""
        self.page_selector.blockSignals(True)
        current_data = self.page_selector.currentData()
        self.page_selector.clear()
        self.page_selector.addItem("Tất cả các Page", None)

        select_index = 0
        for idx, p in enumerate(pages, start=1):
            name = p.get("name", "Fanpage")
            fb_id = p.get("facebook_page_id", "")
            pid = p.get("id")
            label = f"{name} ({fb_id})" if fb_id else name
            self.page_selector.addItem(label, pid)
            if pid == current_data:
                select_index = idx

        self.page_selector.setCurrentIndex(select_index)
        self.page_selector.blockSignals(False)

    def _on_page_selector_changed(self, index: int) -> None:
        page_id = self.page_selector.currentData()
        self.context.set_selected_page(page_id)

    def update_license_display(self, is_active: bool, is_free: bool = False) -> None:
        """Cập nhật giao diện của nút Badge License."""
        if is_free:
            self.btn_license_badge.setText("🎁 Miễn phí")
            self.btn_license_badge.setObjectName("badgeReady")
        elif is_active:
            self.btn_license_badge.setText("✅ Active")
            self.btn_license_badge.setObjectName("badgeReady")
        else:
            self.btn_license_badge.setText("⚠️ Chưa kích hoạt")
            self.btn_license_badge.setObjectName("badgeWarning")

        self.btn_license_badge.style().unpolish(self.btn_license_badge)
        self.btn_license_badge.style().polish(self.btn_license_badge)

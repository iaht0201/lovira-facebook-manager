"""Lovira Workspace 2.0 — Compact Top Command Bar (PySide6).

Drop-in replacement preserving quick_create_clicked, license_badge_clicked,
search_input, page_selector, and the existing public methods.
"""

from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QFrame,
    QSizePolicy,
)

from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.shell.global_context import GlobalPageContext


TOPBAR_QSS = """
QFrame#headerFrame {
    background-color: #172338;
    border: none;
    border-bottom: 1px solid #2B3A52;
}
QFrame#headerFrame QLabel {
    background-color: transparent;
    border: none;
}
QLabel#headerTitle {
    color: #F4F7FD;
    font-size: 16px;
    font-weight: 700;
}
QFrame#headerDivider {
    background-color: #33445D;
    border: none;
}
QLineEdit#searchInput, QComboBox#pageSelector {
    background-color: #22314A;
    border: 1px solid #31435D;
    border-radius: 10px;
    color: #E9EFFA;
    min-height: 34px;
    max-height: 34px;
    padding: 0px 11px;
    font-size: 12px;
    selection-background-color: #6157EA;
}
QLineEdit#searchInput {
    padding-left: 6px;
}
QLineEdit#searchInput:hover, QComboBox#pageSelector:hover {
    border-color: #4E6281;
}
QLineEdit#searchInput:focus, QComboBox#pageSelector:focus {
    border-color: #8B82FF;
    background-color: #253651;
}
QComboBox#pageSelector {
    padding-left: 12px;
    padding-right: 22px;
}
QComboBox#pageSelector::drop-down {
    border: 0;
    width: 24px;
    background: transparent;
}
QComboBox#pageSelector QAbstractItemView {
    background-color: #22314A;
    border: 1px solid #3A4D69;
    border-radius: 8px;
    color: #F4F7FD;
    selection-background-color: #4F46E5;
    padding: 5px;
    outline: none;
}
QPushButton#quickCreateButton {
    background-color: #6257EC;
    border: 1px solid #766CF4;
    border-radius: 10px;
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 650;
    padding: 0 15px;
    min-height: 34px;
    max-height: 34px;
}
QPushButton#quickCreateButton:hover {
    background-color: #756BF3;
}
QPushButton#quickCreateButton:pressed {
    background-color: #5046D4;
}
QPushButton#badgeReady, QPushButton#badgeWarning {
    border-radius: 10px;
    font-size: 11px;
    font-weight: 650;
    padding: 0 12px;
    min-height: 34px;
    max-height: 34px;
}
QPushButton#badgeReady {
    background-color: #123F37;
    color: #75E0BD;
    border: 1px solid #286553;
}
QPushButton#badgeReady:hover {
    background-color: #185346;
}
QPushButton#badgeWarning {
    background-color: #463221;
    color: #FFCB86;
    border: 1px solid #6B4A2B;
}
QPushButton#badgeWarning:hover {
    background-color: #56402A;
}
QPushButton#quickCreateButton:focus,
QPushButton#badgeReady:focus,
QPushButton#badgeWarning:focus {
    border: 1px solid #A59CFF;
}
"""


class TopCommandBar(QFrame):
    """Compact command bar for desktop screens (height: 58px)."""

    quick_create_clicked = Signal()
    license_badge_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("headerFrame")
        self.setFixedHeight(58)
        self.context = GlobalPageContext.get_instance()
        self._init_ui()
        self.setStyleSheet(TOPBAR_QSS)
        self._setup_shortcuts()

    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 7, 18, 7)
        layout.setSpacing(10)

        self.lbl_title = QLabel("Tổng quan")
        self.lbl_title.setObjectName("headerTitle")
        self.lbl_title.setMinimumWidth(90)
        self.lbl_title.setMaximumWidth(165)
        self.lbl_title.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.lbl_title)

        self.divider = QFrame()
        self.divider.setObjectName("headerDivider")
        self.divider.setFixedSize(1, 22)
        layout.addWidget(self.divider)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Tìm bài viết, video, Fanpage...  Ctrl+K")
        self.search_input.setMinimumWidth(145)
        self.search_input.setMaximumWidth(310)
        self.search_input.setFixedHeight(36)
        self.search_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.search_input.addAction(
            get_icon("search", "#A9B8CF", 16),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        layout.addWidget(self.search_input, 2)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(280)
        self._search_timer.timeout.connect(self._apply_search)
        self.search_input.textChanged.connect(self._on_search_edited)
        self.search_input.returnPressed.connect(self._submit_search)

        self.page_selector = QComboBox()
        self.page_selector.setObjectName("pageSelector")
        self.page_selector.setMinimumWidth(155)
        self.page_selector.setMaximumWidth(265)
        self.page_selector.setFixedHeight(36)
        self.page_selector.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.page_selector.addItem("Tất cả Fanpage", None)
        self.page_selector.setToolTip("Lọc theo Fanpage")
        self.page_selector.currentIndexChanged.connect(self._on_page_selector_changed)
        layout.addWidget(self.page_selector, 1)

        layout.addStretch(1)

        self.btn_quick_create = QPushButton("Tạo bài")
        self.btn_quick_create.setObjectName("quickCreateButton")
        self.btn_quick_create.setFixedHeight(36)
        self.btn_quick_create.setIcon(get_icon("composer", "#FFFFFF", 16))
        self.btn_quick_create.setIconSize(self.btn_quick_create.iconSize())
        self.btn_quick_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick_create.setToolTip("Tạo bài mới (Ctrl+N)")
        self.btn_quick_create.clicked.connect(self.quick_create_clicked.emit)
        layout.addWidget(self.btn_quick_create)

        self.btn_license_badge = QPushButton("Chưa kích hoạt")
        self.btn_license_badge.setObjectName("badgeWarning")
        self.btn_license_badge.setFixedHeight(36)
        self.btn_license_badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_license_badge.setToolTip("Xem thông tin bản quyền")
        self.btn_license_badge.clicked.connect(self.license_badge_clicked.emit)
        layout.addWidget(self.btn_license_badge)

    def _setup_shortcuts(self) -> None:
        self.shortcut_search = QShortcut(QKeySequence("Ctrl+K"), self)
        self.shortcut_search.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_search.activated.connect(self.focus_search)

        self.shortcut_new = QShortcut(QKeySequence("Ctrl+N"), self)
        self.shortcut_new.setContext(Qt.ShortcutContext.WindowShortcut)
        self.shortcut_new.activated.connect(self.quick_create_clicked.emit)

    def _on_search_edited(self, _text: str) -> None:
        self._search_timer.start()

    def _apply_search(self) -> None:
        self.context.set_search_query(self.search_input.text())

    def _submit_search(self) -> None:
        self._search_timer.stop()
        query = self.search_input.text()
        self.context.set_search_query(query)
        self.context.submit_search(query)

    def focus_search(self) -> None:
        self.search_input.setFocus()
        self.search_input.selectAll()

    def set_screen_title(self, title: str) -> None:
        self.lbl_title.setText(title)
        self.lbl_title.setToolTip(title)

    def populate_pages(self, pages: List[Dict[str, Any]]) -> None:
        """Preserve selection and reset global filter when a Page disappears."""
        previous = self.page_selector.currentData()
        self.page_selector.blockSignals(True)
        try:
            self.page_selector.clear()
            self.page_selector.addItem("Tất cả Fanpage", None)
            selected_index = 0
            for idx, page in enumerate(pages, start=1):
                internal_id = page.get("id")
                name = page.get("name") or "Fanpage"
                fb_id = str(page.get("facebook_page_id") or "")
                label = f"{name} · {fb_id}" if fb_id else name
                self.page_selector.addItem(label, internal_id)
                self.page_selector.setItemData(
                    idx, label, Qt.ItemDataRole.ToolTipRole
                )
                if internal_id == previous:
                    selected_index = idx
            self.page_selector.setCurrentIndex(selected_index)
        finally:
            self.page_selector.blockSignals(False)

        if self.page_selector.currentData() != previous:
            self.context.set_selected_page(self.page_selector.currentData())

    def _on_page_selector_changed(self, _index: int) -> None:
        self.context.set_selected_page(self.page_selector.currentData())

    def update_license_display(self, is_active: bool, is_free: bool = False) -> None:
        if is_free:
            text, name = "Miễn phí", "badgeReady"
        elif is_active:
            text, name = "Đã kích hoạt", "badgeReady"
        else:
            text, name = "Chưa kích hoạt", "badgeWarning"

        self.btn_license_badge.setText(text)
        self.btn_license_badge.setObjectName(name)
        style = self.btn_license_badge.style()
        style.unpolish(self.btn_license_badge)
        style.polish(self.btn_license_badge)
        self.btn_license_badge.update()

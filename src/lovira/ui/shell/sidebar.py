
"""
Lovira Workspace 2.0 - Modern Compact Sidebar
Native PySide6 Navigation Component

- Expanded: 236px
- Collapsed: 68px
- Modern dark design, rounded buttons
- SVG icons, active route highlight
- Grouped navigation
- Smooth compact layout
- Scrollable menu, fixed footer
- Compatible with existing Navigation Router
"""

from typing import Dict, Optional

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
    QStyle,
)

from src.lovira.ui.design.icons import get_icon
from src.lovira.ui.shell.navigation import (
    Route,
    NAVIGATION_ROUTES,
    RouteItem,
)


# ==========================================================
# SIDEBAR DESIGN SYSTEM
# ==========================================================

SIDEBAR_STYLE = """
/* Root */
QFrame#sidebarFrame {
    background-color: #101A2C;
    border: none;
    border-right: 1px solid #28364D;
}

/* Brand */
QWidget#sidebarBrand {
    background-color: transparent;
    border: none;
}

QFrame#sidebarBrandIcon {
    background-color: #272454;
    border: 1px solid #393576;
    border-radius: 10px;
}

QLabel#sidebarLogoIcon {
    background-color: transparent;
    border: none;
}

QLabel#sidebarBrandTitle {
    background-color: transparent;
    color: #F5F7FC;
    font-size: 16px;
    font-weight: 800;
}

QLabel#sidebarBrandSubtitle {
    background-color: transparent;
    color: #9894FF;
    font-size: 11px;
}

/* Navigation scroll area */
QScrollArea#sidebarScroll {
    background-color: transparent;
    border: none;
}

QWidget#sidebarScrollContent {
    background-color: transparent;
    border: none;
}

/* Group heading */
QLabel#sidebarSectionLabel {
    background-color: transparent;
    color: #71829E;
    font-size: 10px;
    font-weight: 700;
    padding-left: 12px;
    border: none;
}

/* Normal menu button */
QPushButton#sidebarNavButton {
    background-color: transparent;
    color: #A9B8CF;
    border: 1px solid transparent;
    border-left: 3px solid transparent;
    border-radius: 10px;

    text-align: left;
    padding-left: 11px;
    padding-right: 8px;

    font-size: 13px;
    font-weight: 500;
}

/* Hover */
QPushButton#sidebarNavButton:hover {
    background-color: #202E47;
    color: #F3F6FC;
}

/* Selected */
QPushButton#sidebarNavButton:checked {
    background-color: #302D62;
    color: #FFFFFF;
    border: 1px solid #454080;
    border-left: 3px solid #857CFF;
    font-weight: 600;
}

/* Selected hover */
QPushButton#sidebarNavButton:checked:hover {
    background-color: #393574;
}

/* Keyboard focus */
QPushButton#sidebarNavButton:focus {
    border-color: #6D64E8;
}

/* Collapsed navigation */
QPushButton#sidebarNavButton[compact="true"] {
    padding: 0px;
    text-align: center;
}

/* Footer divider */
QFrame#sidebarDivider {
    background-color: #29364C;
    border: none;
    max-height: 1px;
    min-height: 1px;
}

/* Group divider in collapsed mode */
QFrame#sidebarGroupDivider {
    background-color: #26344A;
    border: none;
    max-height: 1px;
    min-height: 1px;
}

/* Collapse button */
QPushButton#sidebarCollapseButton {
    background-color: transparent;
    color: #8192AD;

    border: 1px solid transparent;
    border-radius: 10px;

    text-align: left;
    padding-left: 12px;

    font-size: 12px;
    font-weight: 500;
}

QPushButton#sidebarCollapseButton:hover {
    background-color: #202E47;
    color: #F3F6FC;
}

QPushButton#sidebarCollapseButton[compact="true"] {
    padding: 0px;
    text-align: center;
}

/* Minimal scrollbar */
QScrollBar:vertical {
    background-color: transparent;
    width: 5px;
    margin: 0px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #354663;
    border-radius: 2px;
    min-height: 32px;
}

QScrollBar::handle:vertical:hover {
    background-color: #596B8B;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
    background: transparent;
    border: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    height: 0px;
    background: transparent;
}
"""


# ==========================================================
# APP SIDEBAR
# ==========================================================

class AppSidebar(QFrame):
    """
    Modern navigation sidebar for Lovira Workspace 2.0.

    Compatible public API:
        route_requested(Route)
        collapse_toggled(bool)
        set_active_route(route)
        get_button(route)
        toggle_collapse()
    """

    route_requested = Signal(Route)
    collapse_toggled = Signal(bool)

    EXPANDED_WIDTH = 236
    COLLAPSED_WIDTH = 68

    NAV_HEIGHT = 40
    NAV_ICON_SIZE = 18

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.setObjectName("sidebarFrame")
        self.setFixedWidth(self.EXPANDED_WIDTH)

        self.is_collapsed = False

        self._buttons: Dict[Route, QPushButton] = {}
        self._route_items: Dict[Route, RouteItem] = {}

        self._section_labels = []
        self._section_dividers = []

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        self.setStyleSheet(SIDEBAR_STYLE)

        self._init_ui()
        self._refresh_icons()

    # ======================================================
    # INITIALIZE UI
    # ======================================================

    def _init_ui(self) -> None:

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(8)

        self._create_brand()
        self._create_navigation()
        self._create_footer()

    # ======================================================
    # BRAND HEADER
    # ======================================================

    def _create_brand(self) -> None:

        self.logo_container = QWidget()
        self.logo_container.setObjectName("sidebarBrand")
        self.logo_container.setFixedHeight(58)

        self.logo_layout = QHBoxLayout(self.logo_container)
        self.logo_layout.setContentsMargins(3, 0, 3, 0)
        self.logo_layout.setSpacing(10)

        # Logo tile
        self.logo_icon_frame = QFrame()
        self.logo_icon_frame.setObjectName("sidebarBrandIcon")
        self.logo_icon_frame.setFixedSize(36, 36)

        icon_layout = QVBoxLayout(self.logo_icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)

        self.logo_icon = QLabel()
        self.logo_icon.setObjectName("sidebarLogoIcon")
        self.logo_icon.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.logo_icon.setPixmap(
            get_icon(
                "composer",
                "#A69FFF",
                20
            ).pixmap(20, 20)
        )

        icon_layout.addWidget(self.logo_icon)

        self.logo_layout.addWidget(
            self.logo_icon_frame,
            0,
            Qt.AlignmentFlag.AlignVCenter
        )

        # Brand text
        self.brand_text_container = QWidget()
        self.brand_text_container.setObjectName("sidebarBrand")

        brand_layout = QVBoxLayout(
            self.brand_text_container
        )
        brand_layout.setContentsMargins(0, 0, 0, 0)
        brand_layout.setSpacing(3)

        self.lbl_brand = QLabel("LOVIRA")
        self.lbl_brand.setObjectName(
            "sidebarBrandTitle"
        )

        self.lbl_sub = QLabel("Workspace 2.0")
        self.lbl_sub.setObjectName(
            "sidebarBrandSubtitle"
        )

        brand_layout.addWidget(self.lbl_brand)
        brand_layout.addWidget(self.lbl_sub)

        self.logo_layout.addWidget(
            self.brand_text_container,
            1
        )

        self.main_layout.addWidget(
            self.logo_container
        )

    # ======================================================
    # NAVIGATION
    # ======================================================

    def _create_navigation(self) -> None:

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("sidebarScroll")

        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(
            QFrame.Shape.NoFrame
        )

        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.scroll_area.viewport().setAutoFillBackground(
            False
        )

        self.scroll_area.viewport().setStyleSheet(
            "background: transparent;"
        )

        scroll_content = QWidget()
        scroll_content.setObjectName(
            "sidebarScrollContent"
        )

        self.nav_layout = QVBoxLayout(scroll_content)
        self.nav_layout.setContentsMargins(0, 2, 0, 8)
        self.nav_layout.setSpacing(4)

        current_section = None

        for item in NAVIGATION_ROUTES:

            # Group headings
            if item.section != current_section:
                current_section = item.section

                self._add_section(
                    current_section,
                    is_first=len(self._section_labels) == 0
                )

            self._add_navigation_button(item)

        self.nav_layout.addStretch(1)

        self.scroll_area.setWidget(scroll_content)

        self.main_layout.addWidget(
            self.scroll_area,
            1
        )

    # ======================================================
    # SECTION
    # ======================================================

    def _add_section(
        self,
        section_name: str,
        is_first: bool = False
    ) -> None:

        if not is_first:
            self.nav_layout.addSpacing(9)

        # Divider only shown when collapsed
        divider = QFrame()
        divider.setObjectName(
            "sidebarGroupDivider"
        )
        divider.setFixedSize(26, 1)
        divider.setVisible(False)

        self.nav_layout.addWidget(
            divider,
            0,
            Qt.AlignmentFlag.AlignHCenter
        )

        self._section_dividers.append(
            (divider, is_first)
        )

        # Section title
        section_label = QLabel(
            section_name.upper()
        )
        section_label.setObjectName(
            "sidebarSectionLabel"
        )
        section_label.setFixedHeight(26)

        self.nav_layout.addWidget(section_label)
        self._section_labels.append(section_label)

    # ======================================================
    # NAVIGATION BUTTON
    # ======================================================

    def _add_navigation_button(
        self,
        item: RouteItem
    ) -> None:

        button = QPushButton(item.title)
        button.setObjectName("sidebarNavButton")

        button.setFixedHeight(self.NAV_HEIGHT)
        button.setCheckable(True)

        button.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        button.setIconSize(
            QSize(
                self.NAV_ICON_SIZE,
                self.NAV_ICON_SIZE
            )
        )

        button.setProperty(
            "route_key",
            item.route.value
        )

        button.setProperty(
            "full_title",
            item.title
        )

        button.setProperty(
            "compact",
            False
        )

        button.setToolTip(
            f"{item.title}\n{item.description}"
        )

        button.setAccessibleName(item.title)

        # Default dashboard
        if item.route == Route.DASHBOARD:
            button.setChecked(True)

        button.clicked.connect(
            lambda checked, route=item.route:
            self._on_route_clicked(route)
        )

        self._button_group.addButton(button)

        self._buttons[item.route] = button
        self._route_items[item.route] = item

        self.nav_layout.addWidget(button)

    # ======================================================
    # FOOTER
    # ======================================================

    def _create_footer(self) -> None:

        divider = QFrame()
        divider.setObjectName("sidebarDivider")
        divider.setFixedHeight(1)

        self.main_layout.addWidget(divider)

        self.btn_toggle_collapse = QPushButton(
            "Thu gọn menu"
        )

        self.btn_toggle_collapse.setObjectName(
            "sidebarCollapseButton"
        )

        self.btn_toggle_collapse.setFixedHeight(40)

        self.btn_toggle_collapse.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.btn_toggle_collapse.setIconSize(
            QSize(16, 16)
        )

        self.btn_toggle_collapse.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_ArrowLeft
            )
        )

        self.btn_toggle_collapse.setProperty(
            "compact",
            False
        )

        self.btn_toggle_collapse.setToolTip(
            "Thu gọn thanh điều hướng"
        )

        self.btn_toggle_collapse.clicked.connect(
            self.toggle_collapse
        )

        self.main_layout.addWidget(
            self.btn_toggle_collapse
        )

    # ======================================================
    # ROUTING
    # ======================================================

    def _on_route_clicked(self, route: Route) -> None:
        self.set_active_route(route)
        self.route_requested.emit(route)

    def set_active_route(self, route: Route) -> None:
        """
        Select current route and update its icon.
        """

        button = self._buttons.get(route)

        if button is None:
            return

        if not button.isChecked():
            button.setChecked(True)

        self._refresh_icons()

        # Keep active item visible when window is short
        self.scroll_area.ensureWidgetVisible(
            button,
            8,
            12
        )

    def get_button(
        self,
        route: Route
    ) -> Optional[QPushButton]:

        return self._buttons.get(route)

    # ======================================================
    # ICON STATES
    # ======================================================

    def _refresh_icons(self) -> None:
        """
        Active icons use the accent color.
        Inactive icons use muted slate.
        """

        for route, button in self._buttons.items():

            item = self._route_items[route]

            if button.isChecked():
                icon_color = "#B7B1FF"
            else:
                icon_color = "#889AB4"

            button.setIcon(
                get_icon(
                    item.icon_name,
                    icon_color,
                    self.NAV_ICON_SIZE
                )
            )

    # ======================================================
    # COLLAPSE / EXPAND
    # ======================================================

    def toggle_collapse(self) -> None:
        self.set_collapsed(
            not self.is_collapsed
        )

    def set_collapsed(
        self,
        collapsed: bool
    ) -> None:
        """
        Change sidebar width while keeping
        navigation state unchanged.
        """

        collapsed = bool(collapsed)

        if collapsed == self.is_collapsed:
            return

        self.is_collapsed = collapsed

        if collapsed:
            self._apply_collapsed_state()
        else:
            self._apply_expanded_state()

        self.collapse_toggled.emit(
            self.is_collapsed
        )

    def _apply_collapsed_state(self) -> None:

        # Hide brand text
        self.brand_text_container.hide()

        # Center brand icon
        self.logo_layout.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        # Hide group headings
        for label in self._section_labels:
            label.hide()

        # Show separators between groups
        for divider, is_first in self._section_dividers:
            divider.setVisible(not is_first)

        # Icon-only navigation
        for route, button in self._buttons.items():

            button.setText("")

            button.setProperty(
                "compact",
                True
            )

            self._repolish(button)

        # Footer
        self.btn_toggle_collapse.setText("")

        self.btn_toggle_collapse.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_ArrowRight
            )
        )

        self.btn_toggle_collapse.setProperty(
            "compact",
            True
        )

        self.btn_toggle_collapse.setToolTip(
            "Mở rộng thanh điều hướng"
        )

        self._repolish(
            self.btn_toggle_collapse
        )

        self.setFixedWidth(
            self.COLLAPSED_WIDTH
        )

    def _apply_expanded_state(self) -> None:

        self.setFixedWidth(
            self.EXPANDED_WIDTH
        )

        # Restore brand
        self.brand_text_container.show()

        self.logo_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft |
            Qt.AlignmentFlag.AlignVCenter
        )

        # Show section labels
        for label in self._section_labels:
            label.show()

        # Hide compact separators
        for divider, _ in self._section_dividers:
            divider.hide()

        # Restore navigation text
        for route, button in self._buttons.items():

            item = self._route_items[route]

            button.setText(item.title)

            button.setProperty(
                "compact",
                False
            )

            self._repolish(button)

        # Footer
        self.btn_toggle_collapse.setText(
            "Thu gọn menu"
        )

        self.btn_toggle_collapse.setIcon(
            self.style().standardIcon(
                QStyle.StandardPixmap.SP_ArrowLeft
            )
        )

        self.btn_toggle_collapse.setProperty(
            "compact",
            False
        )

        self.btn_toggle_collapse.setToolTip(
            "Thu gọn thanh điều hướng"
        )

        self._repolish(
            self.btn_toggle_collapse
        )

    # ======================================================
    # STYLE REFRESH
    # ======================================================

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        """
        Refresh QSS after dynamic property changes.
        """

        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

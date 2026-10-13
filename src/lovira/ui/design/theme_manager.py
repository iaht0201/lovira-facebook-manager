"""
Lovira Workspace 2.0 — Theme Engine & Stylesheet Generator
Tự động sinh QSS Stylesheet phân tầng từ Tokens & Density Metrics:
- Không lặp lại bộ chọn (Zero duplicate selectors — A-08)
- Hỗ trợ đồng thời Dark và Light Mode
- Hỗ trợ điều chỉnh Mật độ hiển thị (Comfortable vs Compact)
- Tuân thủ tiêu chuẩn tương phản WCAG AA và focus ring bàn phím
"""

import logging
from typing import Optional
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal

from .tokens import (
    ThemeMode,
    DensityMode,
    ColorTokens,
    DensityMetrics,
    TypographyTokens,
    SpacingTokens,
    get_palette,
    get_density,
)

logger = logging.getLogger(__name__)


def generate_stylesheet(
    mode: ThemeMode = ThemeMode.DARK,
    density_mode: DensityMode = DensityMode.COMFORTABLE,
) -> str:
    """
    Sinh chuỗi QSS Stylesheet đầy đủ từ bảng tokens và density.
    Bảo đảm không có duplicate selector nào.
    """
    c: ColorTokens = get_palette(mode)
    d: DensityMetrics = get_density(density_mode)
    t = TypographyTokens()
    s = SpacingTokens()

    qss = f"""
/* ==========================================================================
   LOVIRA WORKSPACE 2.0 — DESIGN SYSTEM ({mode.value.upper()} | {density_mode.value.upper()})
   ========================================================================== */

/* 1. Global Reset & Base */
QWidget {{
    background-color: {c.bg_canvas};
    color: {c.text_primary};
    font-family: {t.font_family};
    font-size: {t.size_body}px;
    selection-background-color: {c.accent_default};
    selection-color: #FFFFFF;
}}

/* QLabel mặc định phải transparent — tránh hộp nền đen kế thừa từ QWidget trên Windows */
QLabel {{
    background-color: transparent;
    border: none;
}}

/* QFrame mặc định không có nền (thay vì kế thừa) trừ khi có objectName */
QFrame {{
    background-color: transparent;
    border: none;
}}

QMainWindow {{
    background-color: {c.bg_canvas};
}}

QToolTip {{
    background-color: {c.bg_elevated};
    color: {c.text_primary};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_sm}px;
    padding: 6px 10px;
    font-size: {t.size_small}px;
}}

/* 2. App Sidebar */
#sidebarFrame {{
    background-color: {c.bg_sidebar};
    border-right: 1px solid {c.border_subtle};
}}

#logoLabel {{
    font-size: 16px;
    font-weight: {t.weight_bold};
    color: {c.accent_default};
    padding: 14px 16px;
}}

#sidebarSectionLabel {{
    font-size: {t.size_caption}px;
    font-weight: {t.weight_bold};
    color: {c.text_muted};
    text-transform: uppercase;
    padding: 12px 16px 4px 16px;
    letter-spacing: 0.5px;
}}

#sidebarButton {{
    background-color: transparent;
    color: {c.text_secondary};
    text-align: left;
    padding: {d.sidebar_item_padding};
    border-radius: {s.radius_md}px;
    font-weight: {t.weight_medium};
    font-size: {t.size_body}px;
    border: none;
    margin: 2px 8px;
    min-height: 34px;
}}

#sidebarButton:hover {{
    background-color: {c.bg_elevated};
    color: {c.text_primary};
}}

#sidebarButton:checked {{
    background-color: {c.accent_default};
    color: #FFFFFF;
    font-weight: {t.weight_semibold};
}}

#sidebarButton:focus {{
    outline: none;
    border: 1px solid {c.focus_ring};
}}

/* 3. Top Command Bar */
#headerFrame {{
    background-color: {c.bg_surface};
    border-bottom: 1px solid {c.border_subtle};
    padding: 8px 16px;
}}

#searchInput {{
    background-color: {c.bg_elevated};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    color: {c.text_primary};
    padding: {d.input_padding};
    font-size: {t.size_body}px;
    min-height: {d.input_height}px;
}}

#searchInput:focus {{
    border: 1px solid {c.focus_ring};
}}

#pageSelector {{
    background-color: {c.bg_elevated};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    color: {c.text_primary};
    padding: {d.input_padding};
    min-width: 190px;
    min-height: {d.input_height}px;
}}

#pageSelector::drop-down {{
    border: none;
    width: 24px;
}}

#pageSelector QAbstractItemView {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    selection-background-color: {c.accent_default};
    color: {c.text_primary};
    padding: 4px;
}}

/* 4. Form Inputs */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDateTimeEdit {{
    background-color: {c.bg_elevated};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    color: {c.text_primary};
    padding: {d.input_padding};
    min-height: {d.input_height}px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QDateTimeEdit:focus {{
    border: 1px solid {c.focus_ring};
}}

QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    background-color: {c.bg_canvas};
    color: {c.text_muted};
    border-color: {c.border_subtle};
}}

QComboBox {{
    background-color: {c.bg_elevated};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    color: {c.text_primary};
    padding: {d.input_padding};
    min-height: {d.input_height}px;
}}

QComboBox:hover {{
    border-color: {c.accent_default};
}}

QComboBox:focus {{
    border-color: {c.focus_ring};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    selection-background-color: {c.accent_default};
    color: {c.text_primary};
    padding: 6px;
}}

/* 5. Buttons (Đơn nhất, loại bỏ trùng lặp - A-08) */
QPushButton {{
    background-color: {c.bg_elevated};
    color: {c.text_primary};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    padding: {d.button_padding};
    font-weight: {t.weight_medium};
    font-size: {t.size_body}px;
    min-height: {d.button_height}px;
}}

QPushButton:hover {{
    background-color: {c.border_subtle};
    color: {c.text_primary};
}}

QPushButton:pressed {{
    background-color: {c.bg_surface};
}}

QPushButton:focus {{
    outline: none;
    border: 1px solid {c.focus_ring};
}}

QPushButton:disabled {{
    background-color: {c.bg_surface};
    color: {c.text_muted};
    border-color: {c.border_subtle};
}}

QPushButton#primaryButton {{
    background-color: {c.accent_default};
    color: #FFFFFF;
    border: 1px solid {c.accent_default};
    font-weight: {t.weight_semibold};
}}

QPushButton#primaryButton:hover {{
    background-color: {c.accent_hover};
    border-color: {c.accent_hover};
}}

QPushButton#primaryButton:pressed {{
    background-color: {c.accent_active};
}}

QPushButton#successButton {{
    background-color: {c.success};
    color: #FFFFFF;
    border: 1px solid {c.success};
    font-weight: {t.weight_semibold};
}}

QPushButton#successButton:hover {{
    background-color: #10B981;
    border-color: #10B981;
}}

QPushButton#dangerButton {{
    background-color: {c.danger};
    color: #FFFFFF;
    border: 1px solid {c.danger};
    font-weight: {t.weight_semibold};
}}

QPushButton#dangerButton:hover {{
    background-color: #EF4444;
    border-color: #EF4444;
}}

QPushButton#ghostButton {{
    background-color: transparent;
    color: {c.text_secondary};
    border: none;
}}

QPushButton#ghostButton:hover {{
    background-color: {c.bg_elevated};
    color: {c.text_primary};
}}

/* 6. Surface Panels & Cards */
#cardFrame {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_lg}px;
    padding: {d.card_padding}px;
}}

#metricCard {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_lg}px;
    padding: 14px 18px;
    min-height: 100px;
}}

#metricCard:hover {{
    border-color: {c.accent_default};
}}

/* 7. Data Tables */
QTableWidget, QTableView {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_lg}px;
    gridline-color: {c.border_subtle};
    color: {c.text_primary};
    alternate-background-color: {c.bg_canvas};
}}

QHeaderView::section {{
    background-color: {c.bg_canvas};
    color: {c.text_secondary};
    padding: 10px 14px;
    border: none;
    border-bottom: 1px solid {c.border_subtle};
    font-weight: {t.weight_semibold};
    font-size: {t.size_small}px;
}}

QTableWidget::item, QTableView::item {{
    padding: 8px 12px;
    min-height: {d.table_row_height}px;
}}

QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {c.bg_elevated};
    color: {c.text_primary};
}}

/* 8. Tabs */
QTabWidget::pane {{
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_lg}px;
    background-color: {c.bg_surface};
    top: -1px;
}}

QTabBar::tab {{
    background-color: {c.bg_canvas};
    color: {c.text_secondary};
    padding: 9px 18px;
    border: 1px solid {c.border_subtle};
    border-bottom: none;
    border-top-left-radius: {s.radius_md}px;
    border-top-right-radius: {s.radius_md}px;
    margin-right: 4px;
    font-weight: {t.weight_medium};
}}

QTabBar::tab:selected {{
    background-color: {c.bg_surface};
    color: {c.accent_default};
    font-weight: {t.weight_semibold};
    border-bottom: 1px solid {c.bg_surface};
}}

/* 9. Status Badges & Chips */
#badgeReady, #badgeSuccess {{
    background-color: {c.success_bg};
    color: {c.success};
    border-radius: {s.radius_pill}px;
    padding: 3px 10px;
    font-weight: {t.weight_semibold};
    font-size: {t.size_caption}px;
}}

#badgeWarning {{
    background-color: {c.warning_bg};
    color: {c.warning};
    border-radius: {s.radius_pill}px;
    padding: 3px 10px;
    font-weight: {t.weight_semibold};
    font-size: {t.size_caption}px;
}}

#badgeDanger {{
    background-color: {c.danger_bg};
    color: {c.danger};
    border-radius: {s.radius_pill}px;
    padding: 3px 10px;
    font-weight: {t.weight_semibold};
    font-size: {t.size_caption}px;
}}

#badgeInfo {{
    background-color: {c.info_bg};
    color: {c.info};
    border-radius: {s.radius_pill}px;
    padding: 3px 10px;
    font-weight: {t.weight_semibold};
    font-size: {t.size_caption}px;
}}

/* 10. Scrollbars & Sliders */
QScrollBar:vertical {{
    border: none;
    background-color: transparent;
    width: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {c.border_subtle};
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c.text_muted};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    border: none;
    background-color: transparent;
    height: 8px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {c.border_subtle};
    border-radius: 4px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {c.text_muted};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QProgressBar {{
    background-color: {c.bg_elevated};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_sm}px;
    text-align: center;
    color: {c.text_primary};
    min-height: 12px;
}}

QProgressBar::chunk {{
    background-color: {c.accent_default};
    border-radius: {s.radius_sm - 1}px;
}}

/* 11. Context Menus & Popups */
QMenu {{
    background-color: {c.bg_surface};
    border: 1px solid {c.border_subtle};
    border-radius: {s.radius_md}px;
    color: {c.text_primary};
    padding: 4px;
}}

QMenu::item {{
    padding: 8px 24px 8px 12px;
    border-radius: {s.radius_sm}px;
}}

QMenu::item:selected {{
    background-color: {c.accent_default};
    color: #FFFFFF;
}}

QMenu::separator {{
    height: 1px;
    background-color: {c.border_subtle};
    margin: 4px 0;
}}

QStatusBar {{
    background-color: {c.bg_surface};
    border-top: 1px solid {c.border_subtle};
    color: {c.text_secondary};
    font-size: {t.size_small}px;
    padding: 4px 16px;
    min-height: 28px;
}}
"""
    return qss


class ThemeManager(QObject):
    """Quản lý trạng thái Theme toàn cầu cho ứng dụng."""

    theme_changed = Signal(str, str)

    _instance: Optional["ThemeManager"] = None

    def __init__(self):
        super().__init__()
        self._current_mode: ThemeMode = ThemeMode.DARK
        self._current_density: DensityMode = DensityMode.COMFORTABLE

    @classmethod
    def get_instance(cls) -> "ThemeManager":
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def current_mode(self) -> ThemeMode:
        return self._current_mode

    @property
    def current_density(self) -> DensityMode:
        return self._current_density

    def apply_theme(
        self,
        app: Optional[QApplication] = None,
        mode: Optional[ThemeMode] = None,
        density: Optional[DensityMode] = None,
    ) -> None:
        """Áp dụng theme lên QApplication."""
        if mode is not None:
            self._current_mode = mode
        if density is not None:
            self._current_density = density

        target_app = app or QApplication.instance()
        if target_app:
            stylesheet = generate_stylesheet(self._current_mode, self._current_density)
            target_app.setStyleSheet(stylesheet)
            logger.info(f"Đã cập nhật giao diện: Theme={self._current_mode.value}, Density={self._current_density.value}")

        self.theme_changed.emit(self._current_mode.value, self._current_density.value)

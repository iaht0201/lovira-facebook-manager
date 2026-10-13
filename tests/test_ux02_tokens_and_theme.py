"""
Kiểm thử chuyên biệt cho Task UX-02: Design Tokens & Theme Engine (DoD Compliance)
- Kiểm tra độ tương phản màu sắc WCAG AA
- Linter kiểm tra Stylesheet QSS không có selector trùng lặp (A-08)
- Kiểm tra hiển thị QIcon vector đa kích thước
- Kiểm tra ThemeManager chuyển đổi Dark/Light và Comfortable/Compact
"""

import re
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QColor

from src.lovira.ui.design.tokens import (
    ThemeMode,
    DensityMode,
    DARK_PALETTE,
    LIGHT_PALETTE,
    get_palette,
    get_density,
)
from src.lovira.ui.design.theme_manager import generate_stylesheet, ThemeManager
from src.lovira.ui.design.icons import SVG_PATHS, get_icon, render_svg_xml
from src.lovira.ui.theme import THEME_DARK, THEME_LIGHT


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def hex_to_luminance(hex_color: str) -> float:
    """Tính relative luminance theo chuẩn WCAG 2.1."""
    color = QColor(hex_color)
    r = color.redF()
    g = color.greenF()
    b = color.blueF()

    def channel_lum(val: float) -> float:
        return val / 12.92 if val <= 0.03928 else ((val + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel_lum(r) + 0.7152 * channel_lum(g) + 0.0722 * channel_lum(b)


def calculate_contrast(hex1: str, hex2: str) -> float:
    """Tính tỷ lệ tương phản contrast ratio giữa 2 màu hex."""
    lum1 = hex_to_luminance(hex1)
    lum2 = hex_to_luminance(hex2)
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def test_color_palettes_wcag_contrast():
    """DoD UX-02: Kiểm tra độ tương phản WCAG AA >= 4.5:1 cho text_primary trên nền canvas & surface."""
    # Dark Mode
    dark_contrast_canvas = calculate_contrast(DARK_PALETTE.text_primary, DARK_PALETTE.bg_canvas)
    dark_contrast_surface = calculate_contrast(DARK_PALETTE.text_primary, DARK_PALETTE.bg_surface)
    assert dark_contrast_canvas >= 4.5, f"Dark canvas contrast quá thấp: {dark_contrast_canvas:.2f}"
    assert dark_contrast_surface >= 4.5, f"Dark surface contrast quá thấp: {dark_contrast_surface:.2f}"

    # Light Mode
    light_contrast_canvas = calculate_contrast(LIGHT_PALETTE.text_primary, LIGHT_PALETTE.bg_canvas)
    light_contrast_surface = calculate_contrast(LIGHT_PALETTE.text_primary, LIGHT_PALETTE.bg_surface)
    assert light_contrast_canvas >= 4.5, f"Light canvas contrast quá thấp: {light_contrast_canvas:.2f}"
    assert light_contrast_surface >= 4.5, f"Light surface contrast quá thấp: {light_contrast_surface:.2f}"


def test_stylesheet_zero_duplicate_selectors():
    """DoD UX-02 & Audit A-08: Linter kiểm tra không có duplicate selector trong chuỗi QSS sinh ra."""
    for mode in [ThemeMode.DARK, ThemeMode.LIGHT]:
        for density in [DensityMode.COMFORTABLE, DensityMode.COMPACT]:
            qss = generate_stylesheet(mode, density)

            # Lấy tất cả các selector trước dấu {
            # Loại bỏ các comment CSS
            clean_qss = re.sub(r"/\*.*?\*/", "", qss, flags=re.DOTALL)
            rules = re.findall(r"([^{}]+)\{", clean_qss)

            selectors_seen = set()
            duplicates = []

            for r in rules:
                # Một rule có thể gồm nhiều selector cách nhau bởi dấu phẩy
                parts = [p.strip() for p in r.split(",") if p.strip()]
                for sel in parts:
                    # Chuẩn hóa khoảng trắng
                    normalized_sel = re.sub(r"\s+", " ", sel)
                    if normalized_sel in selectors_seen:
                        duplicates.append(normalized_sel)
                    selectors_seen.add(normalized_sel)

            assert len(duplicates) == 0, f"Phát hiện selector bị trùng lặp trong {mode.value}/{density.value}: {duplicates}"


def test_density_modes_metrics():
    """DoD UX-02: Kiểm tra cấu hình số liệu hiển thị theo DensityMode."""
    comf = get_density(DensityMode.COMFORTABLE)
    comp = get_density(DensityMode.COMPACT)

    assert comf.button_height > comp.button_height
    assert comf.table_row_height > comp.table_row_height
    assert comf.card_padding > comp.card_padding


def test_svg_vector_icon_rendering(qapp):
    """DoD UX-02: Kiểm tra icon registry render được tất cả biểu tượng vector thành QIcon hợp lệ."""
    # Kiểm tra tất cả các route và action icons
    test_keys = ["dashboard", "composer", "pages", "schedule", "media", "downloads", "bulk_import", "comments", "activity", "settings", "check", "plus", "trash"]

    for k in test_keys:
        assert k in SVG_PATHS, f"Thiếu key icon {k} trong registry!"
        icon = get_icon(k, color="#6258E8", size=24)
        assert isinstance(icon, QIcon)
        assert not icon.isNull()
        # Kiểm tra render pixmap
        pixmap = icon.pixmap(24, 24)
        assert not pixmap.isNull()
        assert pixmap.width() == 24
        assert pixmap.height() == 24


def test_theme_manager_switch_and_signal(qapp):
    """DoD UX-02: Kiểm tra ThemeManager chuyển đổi theme và phát signal."""
    mgr = ThemeManager.get_instance()
    signals_received = []

    mgr.theme_changed.connect(lambda m, d: signals_received.append((m, d)))

    mgr.apply_theme(app=qapp, mode=ThemeMode.LIGHT, density=DensityMode.COMPACT)
    assert mgr.current_mode == ThemeMode.LIGHT
    assert mgr.current_density == DensityMode.COMPACT
    assert len(signals_received) == 1
    assert signals_received[0] == ("light", "compact")

    # Đổi lại về Dark Comfortable mặc định
    mgr.apply_theme(app=qapp, mode=ThemeMode.DARK, density=DensityMode.COMFORTABLE)
    assert mgr.current_mode == ThemeMode.DARK
    assert mgr.current_density == DensityMode.COMFORTABLE
    assert len(signals_received) == 2

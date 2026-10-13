"""
Lovira-Facebook Manager
Theme & Design System Entrypoint (PySide6 QSS)
Tương thích ngược và chuyển tiếp tới hệ thống Design Tokens mới:
- src.lovira.ui.design.tokens (Bảng token Dark & Light)
- src.lovira.ui.design.theme_manager (Trình tạo stylesheet phân tầng không trùng lặp)
"""

from src.lovira.ui.design.tokens import ThemeMode, DensityMode, get_palette, get_density
from src.lovira.ui.design.theme_manager import generate_stylesheet, ThemeManager

# Stylesheet Dark & Light tương thích ngược chuẩn hóa (Zero duplicate selectors — A-08)
THEME_DARK = generate_stylesheet(ThemeMode.DARK, DensityMode.COMFORTABLE)
THEME_LIGHT = generate_stylesheet(ThemeMode.LIGHT, DensityMode.COMFORTABLE)


def get_theme_stylesheet(mode: str = "dark", density: str = "comfortable") -> str:
    """Hàm tiện ích lấy chuỗi stylesheet theo chế độ."""
    tm = ThemeMode.DARK if mode.lower() == "dark" else ThemeMode.LIGHT
    dm = DensityMode.COMPACT if density.lower() == "compact" else DensityMode.COMFORTABLE
    return generate_stylesheet(tm, dm)

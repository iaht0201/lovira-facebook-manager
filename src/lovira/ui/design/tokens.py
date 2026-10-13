"""
Lovira Workspace 2.0 — Design Tokens
Bảng token thiết kế quy chuẩn cho giao diện Desktop PySide6:
- Hệ màu Dark & Light mode (Section 3.1)
- Typography Segoe UI & thang bậc kích thước (Section 3.2)
- Bo góc, khoảng cách, padding và density (Section 3.3)
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any


class ThemeMode(str, Enum):
    DARK = "dark"
    LIGHT = "light"


class DensityMode(str, Enum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


@dataclass(frozen=True)
class ColorTokens:
    bg_canvas: str
    bg_sidebar: str
    bg_surface: str
    bg_elevated: str
    border_subtle: str
    border_focus: str
    text_primary: str
    text_secondary: str
    text_muted: str
    accent_default: str
    accent_hover: str
    accent_active: str
    success: str
    success_bg: str
    warning: str
    warning_bg: str
    danger: str
    danger_bg: str
    info: str
    info_bg: str
    focus_ring: str


DARK_PALETTE = ColorTokens(
    bg_canvas="#0B1220",
    bg_sidebar="#101B2D",
    bg_surface="#162238",
    bg_elevated="#1D2C45",
    border_subtle="#2A3B56",
    border_focus="#6258E8",
    text_primary="#F3F6FC",
    text_secondary="#A9B8CF",
    text_muted="#64748B",
    accent_default="#6258E8",
    accent_hover="#766DF1",
    accent_active="#5147D7",
    success="#24C89A",
    success_bg="#064E3B",
    warning="#F3B85C",
    warning_bg="#78350F",
    danger="#F0707B",
    danger_bg="#7F1D1D",
    info="#66BFFF",
    info_bg="#0C4A6E",
    focus_ring="#9B93FA",
)

LIGHT_PALETTE = ColorTokens(
    bg_canvas="#F5F7FB",
    bg_sidebar="#FFFFFF",
    bg_surface="#FFFFFF",
    bg_elevated="#F8FAFC",
    border_subtle="#E2E8F0",
    border_focus="#5547DF",
    text_primary="#162136",
    text_secondary="#64748B",
    text_muted="#94A3B8",
    accent_default="#5547DF",
    accent_hover="#483AC7",
    accent_active="#3C2DB5",
    success="#047857",
    success_bg="#D1FAE5",
    warning="#9A6700",
    warning_bg="#FEF3C7",
    danger="#C62837",
    danger_bg="#FEE2E2",
    info="#176BA0",
    info_bg="#E0F2FE",
    focus_ring="#4F46E5",
)


@dataclass(frozen=True)
class TypographyTokens:
    font_family: str = '"Segoe UI"'
    size_hero: int = 28
    size_title: int = 22
    size_section: int = 17
    size_body: int = 14
    size_small: int = 12
    size_caption: int = 11

    weight_regular: int = 400
    weight_medium: int = 500
    weight_semibold: int = 600
    weight_bold: int = 700


@dataclass(frozen=True)
class SpacingTokens:
    space_xxs: int = 4
    space_xs: int = 8
    space_sm: int = 12
    space_md: int = 16
    space_lg: int = 20
    space_xl: int = 24
    space_xxl: int = 32

    radius_sm: int = 6
    radius_md: int = 8
    radius_lg: int = 12
    radius_pill: int = 999


@dataclass(frozen=True)
class DensityMetrics:
    button_height: int
    button_padding: str
    input_height: int
    input_padding: str
    table_row_height: int
    card_padding: int
    sidebar_item_padding: str


DENSITY_COMFORTABLE = DensityMetrics(
    button_height=38,
    button_padding="8px 16px",
    input_height=38,
    input_padding="8px 14px",
    table_row_height=44,
    card_padding=18,
    sidebar_item_padding="11px 16px",
)

DENSITY_COMPACT = DensityMetrics(
    button_height=32,
    button_padding="6px 12px",
    input_height=32,
    input_padding="6px 10px",
    table_row_height=36,
    card_padding=12,
    sidebar_item_padding="8px 12px",
)


def get_palette(mode: ThemeMode = ThemeMode.DARK) -> ColorTokens:
    """Lấy bảng màu theo ThemeMode."""
    return DARK_PALETTE if mode == ThemeMode.DARK else LIGHT_PALETTE


def get_density(density: DensityMode = DensityMode.COMFORTABLE) -> DensityMetrics:
    """Lấy số liệu mật độ hiển thị theo DensityMode."""
    return DENSITY_COMFORTABLE if density == DensityMode.COMFORTABLE else DENSITY_COMPACT

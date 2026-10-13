"""
Lovira-Facebook Manager
Theme & Design System (PySide6 QSS)
- Thiết kế Dark Theme hiện đại, sang trọng theo phong cách Slate / Indigo
- Bảng màu hài hòa, độ tương phản chuẩn WCAG AA
- Bo góc, viền và thanh cuộn tinh tế
"""

THEME_DARK = """
/* Global Reset & Base */
QWidget {
    background-color: #0F172A;
    color: #F8FAFC;
    font-family: "Segoe UI", "SF Pro Display", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
    selection-background-color: #6366F1;
    selection-color: #FFFFFF;
}

/* Main Window */
QMainWindow {
    background-color: #0F172A;
}

/* Sidebar */
#sidebarFrame {
    background-color: #1E293B;
    border-right: 1px solid #334155;
}

#logoLabel {
    font-size: 16px;
    font-weight: 700;
    color: #818CF8;
    padding: 12px 8px;
}

#sidebarButton {
    background-color: transparent;
    color: #94A3B8;
    text-align: left;
    padding: 10px 14px;
    border-radius: 8px;
    font-weight: 500;
    font-size: 13px;
    border: none;
    margin: 2px 8px;
}

#sidebarButton:hover {
    background-color: #334155;
    color: #F8FAFC;
}

#sidebarButton:checked {
    background-color: #6366F1;
    color: #FFFFFF;
    font-weight: 600;
}

/* Top Header */
#headerFrame {
    background-color: #1E293B;
    border-bottom: 1px solid #334155;
    padding: 8px 16px;
}

#searchInput {
    background-color: #0F172A;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #F8FAFC;
    padding: 6px 12px;
    font-size: 12px;
}
#searchInput:focus {
    border: 1px solid #6366F1;
}

#pageSelector {
    background-color: #0F172A;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #F8FAFC;
    padding: 6px 12px;
    min-width: 180px;
}
#pageSelector::drop-down {
    border: none;
    width: 20px;
}
#pageSelector QAbstractItemView {
    background-color: #1E293B;
    border: 1px solid #334155;
    selection-background-color: #6366F1;
    color: #F8FAFC;
    padding: 4px;
}

/* General QComboBox */
QComboBox {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #F8FAFC;
    padding: 6px 12px;
    min-height: 20px;
}
QComboBox:hover {
    border-color: #6366F1;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #1E293B;
    border: 1px solid #334155;
    selection-background-color: #6366F1;
    color: #F8FAFC;
    padding: 4px;
}

/* Buttons */
QPushButton {
    background-color: #334155;
    color: #F8FAFC;
    border: 1px solid #475569;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 500;
    min-height: 18px;
}

QPushButton:hover {
    background-color: #475569;
    border-color: #64748B;
}

QPushButton:pressed {
    background-color: #1E293B;
}

QPushButton:disabled {
    background-color: #1E293B;
    color: #64748B;
    border-color: #334155;
}

QPushButton#primaryButton {
    background-color: #4F46E5;
    color: #FFFFFF;
    border: 1px solid #4338CA;
    font-weight: 600;
}

QPushButton#primaryButton:hover {
    background-color: #4338CA;
    border-color: #3730A3;
}

QPushButton#primaryButton:pressed {
    background-color: #312E81;
}

QPushButton#successButton {
    background-color: #059669;
    color: #FFFFFF;
    border: 1px solid #047857;
    font-weight: 600;
}
QPushButton#successButton:hover {
    background-color: #047857;
}

QPushButton#dangerButton {
    background-color: #DC2626;
    color: #FFFFFF;
    border: 1px solid #B91C1C;
    font-weight: 500;
}
QPushButton#dangerButton:hover {
    background-color: #B91C1C;
}

QPushButton#primaryButton:hover {
    background-color: #4F46E5;
}

QPushButton#primaryButton:pressed {
    background-color: #4338CA;
}

QPushButton#successButton {
    background-color: #10B981;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}
QPushButton#successButton:hover {
    background-color: #059669;
}

QPushButton#dangerButton {
    background-color: #EF4444;
    color: #FFFFFF;
    border: none;
}
QPushButton#dangerButton:hover {
    background-color: #DC2626;
}

/* Input Fields */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDateTimeEdit {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    color: #F8FAFC;
    padding: 8px 12px;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QDateTimeEdit:focus {
    border: 1px solid #6366F1;
}

/* Cards & Frames */
#cardFrame {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 16px;
}

/* QTableWidget & QTableView */
QTableWidget, QTableView {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    gridline-color: #334155;
    color: #F8FAFC;
}

QHeaderView::section {
    background-color: #0F172A;
    color: #94A3B8;
    padding: 8px 12px;
    border: none;
    border-bottom: 1px solid #334155;
    font-weight: 600;
    font-size: 12px;
}

QTableWidget::item:selected, QTableView::item:selected {
    background-color: #312E81;
    color: #FFFFFF;
}

/* QTabWidget */
QTabWidget::pane {
    border: 1px solid #334155;
    border-radius: 8px;
    background-color: #1E293B;
    top: -1px;
}

QTabBar::tab {
    background-color: #0F172A;
    color: #94A3B8;
    padding: 8px 16px;
    border: 1px solid #334155;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}

QTabBar::tab:selected {
    background-color: #1E293B;
    color: #818CF8;
    font-weight: 600;
    border-bottom: 1px solid #1E293B;
}

/* Status Bar */
QStatusBar {
    background-color: #1E293B;
    border-top: 1px solid #334155;
    color: #94A3B8;
    font-size: 12px;
    padding: 4px 12px;
}

/* Badges */
#badgeReady {
    background-color: #064E3B;
    color: #34D399;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 11px;
}

#badgeWarning {
    background-color: #78350F;
    color: #FBBF24;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 11px;
}

#badgeDanger {
    background-color: #7F1D1D;
    color: #F87171;
    border-radius: 4px;
    padding: 2px 8px;
    font-weight: 600;
    font-size: 11px;
}

/* Scrollbars */
QScrollBar:vertical {
    border: none;
    background-color: #0F172A;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background-color: #334155;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #475569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""

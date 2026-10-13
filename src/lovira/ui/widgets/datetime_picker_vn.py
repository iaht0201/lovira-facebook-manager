"""
Lovira Workspace 2.0 — DateTimePickerVN Primitive
Widget chọn ngày giờ chuẩn hóa theo múi giờ Việt Nam (UTC+7) (Section 0.1, 5.2):
- Luôn hiển thị nhãn múi giờ Việt Nam rõ ràng, không gây nhầm lẫn múi giờ máy tính
- Chuyển đổi chính xác hai chiều với chuỗi ISO-8601 UTC lưu trong SQLite
- Kiểm tra hợp lệ thời gian hẹn giờ (phải ở tương lai, có buffer an toàn)
"""

from datetime import datetime, timedelta
from typing import Optional
from PySide6.QtCore import Qt, QDateTime, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDateTimeEdit

from src.lovira.domain.timezone import (
    vn_now,
    vn_datetime_to_utc_iso,
    create_vn_datetime,
    VIETNAM_TZ,
)
from src.lovira.ui.design.icons import get_icon


class DateTimePickerVN(QWidget):
    """Bộ chọn ngày giờ chuẩn Việt Nam (UTC+7)."""

    datetime_changed = Signal(str)  # Phát ra chuỗi ISO UTC

    def __init__(
        self,
        default_offset_hours: int = 2,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.default_offset_hours = default_offset_hours
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Hàng input và icon
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        lbl_icon = QLabel()
        lbl_icon.setPixmap(get_icon("clock", "#6258E8", 18).pixmap(18, 18))
        input_row.addWidget(lbl_icon)

        self.dt_edit = QDateTimeEdit()
        self.dt_edit.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.dt_edit.setCalendarPopup(True)

        # Mặc định thời gian: Hiện tại VN + offset
        now = vn_now() + timedelta(hours=self.default_offset_hours)
        qdt = QDateTime(now.year, now.month, now.day, now.hour, now.minute, 0)
        self.dt_edit.setDateTime(qdt)
        self.dt_edit.setMinimumDateTime(QDateTime(now.year, now.month, now.day, 0, 0, 0))
        self.dt_edit.dateTimeChanged.connect(self._on_dt_changed)
        input_row.addWidget(self.dt_edit, stretch=1)

        layout.addLayout(input_row)

        # Nhãn chú thích múi giờ
        self.lbl_note = QLabel("Múi giờ Việt Nam (UTC+7) — Lịch sẽ chạy theo giờ hiển thị này")
        self.lbl_note.setStyleSheet("color: #6258E8; font-size: 11px; font-weight: 500;")
        layout.addWidget(self.lbl_note)

    def _on_dt_changed(self, qdt: QDateTime) -> None:
        utc_iso = self.get_utc_iso()
        self.datetime_changed.emit(utc_iso)

    def get_vn_datetime(self) -> datetime:
        """Lấy datetime có gắn múi giờ Asia/Ho_Chi_Minh."""
        qdt = self.dt_edit.dateTime()
        d = qdt.date()
        t = qdt.time()
        return create_vn_datetime(d.year(), d.month(), d.day(), t.hour(), t.minute(), 0)

    def get_utc_iso(self) -> str:
        """Chuyển đổi thời gian chọn sang chuỗi ISO UTC lưu trữ."""
        dt_vn = self.get_vn_datetime()
        return vn_datetime_to_utc_iso(dt_vn)

    def is_valid_future_time(self, buffer_minutes: int = 2) -> bool:
        """Kiểm tra thời gian có nằm ở tương lai hay không."""
        dt_vn = self.get_vn_datetime()
        min_allowed = vn_now() + timedelta(minutes=buffer_minutes)
        return dt_vn > min_allowed

    def set_datetime_vn(self, dt_vn: datetime) -> None:
        """Đặt thời gian theo datetime VN."""
        qdt = QDateTime(dt_vn.year, dt_vn.month, dt_vn.day, dt_vn.hour, dt_vn.minute, 0)
        self.dt_edit.setDateTime(qdt)

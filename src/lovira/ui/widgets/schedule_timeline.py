"""
Lovira Workspace 2.0 — ScheduleTimelineWidget
Widget dòng thời gian 7 ngày trực quan cho lịch đăng Reels/Post:
- Thống kê số lượng bài đăng theo từng ngày (từ Hôm nay đến 6 ngày tới theo giờ Việt Nam)
- Phân biệt lịch đã lên lịch trên máy và lịch đã đăng
- Giao diện thẻ trực quan với highlight ngày hôm nay
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QFrame,
)
from src.lovira.domain.timezone import vn_now, utc_to_vn


class DayTimelineCard(QFrame):
    """Thẻ biểu diễn một ngày trong 7 ngày tới."""

    clicked = Signal(datetime)

    def __init__(
        self,
        dt_vn: datetime,
        is_today: bool = False,
        count: int = 0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.dt_vn = dt_vn
        self.is_today = is_today
        self.count = count
        self._init_ui()

    def _init_ui(self) -> None:
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(3)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(88)

        # 1. Nhãn Ngày
        day_names = ["Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật"]
        weekday_str = "Hôm nay" if self.is_today else day_names[self.dt_vn.weekday()]
        date_str = f"{self.dt_vn.day:02d}/{self.dt_vn.month:02d}"

        self.lbl_day = QLabel(weekday_str)
        self.lbl_day.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_day.setStyleSheet(
            f"font-size: 11px; font-weight: {'700' if self.is_today else '600'}; "
            f"color: {'#6258E8' if self.is_today else '#94A3B8'};"
        )
        layout.addWidget(self.lbl_day)

        self.lbl_date = QLabel(date_str)
        self.lbl_date.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_date.setStyleSheet("font-size: 10px; color: #64748B;")
        layout.addWidget(self.lbl_date)

        # 2. Số lượng bài — gộp count + unit vào 1 row để tránh clipping
        count_label_str = f"{self.count} bài"
        count_color = "#24C89A" if self.count > 0 else "#64748B"
        self.lbl_count = QLabel(count_label_str)
        self.lbl_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_count.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {count_color};"
        )
        layout.addWidget(self.lbl_count)

        self._update_style()

    def _update_style(self) -> None:
        bg = "#1E2A44" if self.is_today else "#141D2D"
        border = "#6258E8" if self.is_today else "#22314E"
        self.setStyleSheet(f"""
            DayTimelineCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
            DayTimelineCard:hover {{
                border-color: #7A71EE;
                background-color: #243352;
            }}
        """)

    def set_count(self, count: int) -> None:
        self.count = count
        count_color = "#24C89A" if self.count > 0 else "#64748B"
        self.lbl_count.setText(f"{count} bài")
        self.lbl_count.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {count_color};"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.dt_vn)
        super().mousePressEvent(event)


class ScheduleTimelineWidget(QFrame):
    """Widget dải thời gian 7 ngày hiển thị mật độ bài đăng."""

    day_selected = Signal(datetime)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.cards: List[DayTimelineCard] = []
        self._init_ui()

    def _init_ui(self) -> None:
        self.setObjectName("cardFrame")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # Header của Timeline
        header = QHBoxLayout()
        lbl_title = QLabel("KẾ HOẠCH BÀI ĐĂNG 7 NGÀY TỚI")
        lbl_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #94A3B8; letter-spacing: 0.5px;")
        header.addWidget(lbl_title)
        header.addStretch()

        self.lbl_summary = QLabel("0 bài đăng được lên lịch")
        self.lbl_summary.setStyleSheet("font-size: 11px; color: #6258E8; font-weight: 600;")
        header.addWidget(self.lbl_summary)
        layout.addLayout(header)

        # Dải 7 thẻ ngày
        days_layout = QHBoxLayout()
        days_layout.setSpacing(8)

        now = vn_now()
        today = datetime(now.year, now.month, now.day, tzinfo=now.tzinfo)

        for i in range(7):
            target_date = today + timedelta(days=i)
            card = DayTimelineCard(dt_vn=target_date, is_today=(i == 0))
            card.clicked.connect(self.day_selected.emit)
            self.cards.append(card)
            days_layout.addWidget(card)

        layout.addLayout(days_layout)

    def update_with_jobs(self, jobs: List[Dict[str, Any]]) -> None:
        """Đếm số bài viết theo từng ngày trong 7 ngày tới."""
        now = vn_now()
        today_date = now.date()

        counts = {i: 0 for i in range(7)}
        total_in_window = 0

        for job in jobs:
            sched_str = job.get("scheduled_at_utc")
            if not sched_str:
                continue
            try:
                # Chuyển ISO UTC sang VN datetime
                from src.lovira.domain.timezone import utc_iso_to_vn_datetime
                dt_vn = utc_iso_to_vn_datetime(sched_str)
                delta_days = (dt_vn.date() - today_date).days
                if 0 <= delta_days < 7:
                    counts[delta_days] += 1
                    total_in_window += 1
            except Exception:
                continue

        for i, card in enumerate(self.cards):
            card.set_count(counts.get(i, 0))

        self.lbl_summary.setText(f"{total_in_window} bài đăng trong 7 ngày tới")

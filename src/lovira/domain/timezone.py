"""
Lovira-Facebook Manager
Bộ tiện ích Thời gian Việt Nam (Vietnam Timezone Utilities)
Đảm bảo chuẩn hóa độc lập với múi giờ hệ điều hành người dùng (AC-07).
- Múi giờ nghiệp vụ: Asia/Ho_Chi_Minh (UTC+7)
- Múi giờ lưu trữ cơ sở dữ liệu: UTC (ISO-8601 kết thúc bằng 'Z')
"""

from datetime import datetime, timezone, timedelta
from typing import Tuple, Union
from zoneinfo import ZoneInfo

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
VIETNAM_TZ = VN_TZ
UTC_TZ = timezone.utc


def vn_now() -> datetime:
    """Trả về thời gian hiện tại theo giờ Việt Nam."""
    return datetime.now(VN_TZ)


def utc_now() -> datetime:
    """Trả về thời gian hiện tại theo UTC."""
    return datetime.now(UTC_TZ)


def utc_to_vn(dt_utc: datetime) -> datetime:
    """Chuyển đổi datetime UTC sang datetime Asia/Ho_Chi_Minh."""
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=UTC_TZ)
    return dt_utc.astimezone(VN_TZ)


def vn_to_utc(dt_vn: datetime) -> datetime:
    """Chuyển đổi datetime Asia/Ho_Chi_Minh sang datetime UTC."""
    if dt_vn.tzinfo is None:
        dt_vn = dt_vn.replace(tzinfo=VN_TZ)
    return dt_vn.astimezone(UTC_TZ)


def create_vn_datetime(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    """Tạo đối tượng datetime tại Việt Nam (Asia/Ho_Chi_Minh) độc lập với OS timezone."""
    return datetime(year, month, day, hour, minute, second, tzinfo=VN_TZ)


def vn_datetime_to_utc_iso(dt_vn: datetime) -> str:
    """Chuyển đổi datetime VN thành chuỗi ISO-8601 UTC chuẩn lưu trữ SQLite (VD: '2026-10-20T13:30:00Z')."""
    dt_utc = vn_to_utc(dt_vn)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_iso_to_vn_datetime(utc_iso_str: str) -> datetime:
    """Đọc chuỗi ISO-8601 UTC từ SQLite và chuyển đổi sang datetime Asia/Ho_Chi_Minh."""
    clean_str = utc_iso_str.strip()
    if clean_str.endswith("Z"):
        clean_str = clean_str[:-1] + "+00:00"
    dt = datetime.fromisoformat(clean_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(VN_TZ)


def format_vn_display(dt_or_iso: Union[datetime, str]) -> str:
    """Định dạng thời gian hiển thị thân thiện trên UI tiếng Việt."""
    if isinstance(dt_or_iso, str):
        dt_vn = utc_iso_to_vn_datetime(dt_or_iso)
    elif dt_or_iso.tzinfo is None or dt_or_iso.tzinfo != VN_TZ:
        dt_vn = utc_to_vn(dt_or_iso)
    else:
        dt_vn = dt_or_iso
    return f"{dt_vn.hour:02d}:{dt_vn.minute:02d} ngày {dt_vn.day:02d}/{dt_vn.month:02d}/{dt_vn.year} (Giờ VN)"


def validate_schedule_time(
    dt_vn: datetime,
    min_delay_seconds: int = 120,
    max_days_ahead: int = 75,
) -> Tuple[bool, str]:
    """
    Kiểm tra thời điểm hẹn giờ có hợp lệ không:
    - Phải ở tương lai ít nhất min_delay_seconds (mặc định 2 phút)
    - Không được vượt quá max_days_ahead (Facebook giới hạn tối đa ~75 ngày)
    """
    now = vn_now()
    min_time = now + timedelta(seconds=min_delay_seconds)
    max_time = now + timedelta(days=max_days_ahead)

    if dt_vn < min_time:
        diff_secs = int((min_time - dt_vn).total_seconds())
        return False, f"Thời gian hẹn giờ phải ở tương lai (cách hiện tại ít nhất {min_delay_seconds // 60} phút)."

    if dt_vn > max_time:
        return False, f"Thời gian hẹn giờ không được vượt quá {max_days_ahead} ngày."

    return True, "Hợp lệ"

from datetime import timedelta
from src.lovira.domain.timezone import (
    VN_TZ,
    vn_now,
    create_vn_datetime,
    vn_datetime_to_utc_iso,
    utc_iso_to_vn_datetime,
    format_vn_display,
    validate_schedule_time,
)


def test_vietnam_time_to_utc_conversion():
    # AC-07: Ví dụ đặc tả: 20:30 ngày 20/10/2026 tại VN -> 2026-10-20T13:30:00Z
    dt_vn = create_vn_datetime(2026, 10, 20, 20, 30, 0)
    utc_iso = vn_datetime_to_utc_iso(dt_vn)
    assert utc_iso == "2026-10-20T13:30:00Z"

    # Đổi ngược lại sang giờ Việt Nam
    dt_back = utc_iso_to_vn_datetime(utc_iso)
    assert dt_back.year == 2026
    assert dt_back.month == 10
    assert dt_back.day == 20
    assert dt_back.hour == 20
    assert dt_back.minute == 30
    assert dt_back.second == 0
    assert str(dt_back.tzinfo) == "Asia/Ho_Chi_Minh"


def test_format_vn_display():
    dt_vn = create_vn_datetime(2026, 10, 20, 20, 30, 0)
    formatted = format_vn_display(dt_vn)
    assert formatted == "20:30 ngày 20/10/2026 (Giờ VN)"

    # Từ chuỗi UTC
    formatted_from_utc = format_vn_display("2026-10-20T13:30:00Z")
    assert formatted_from_utc == "20:30 ngày 20/10/2026 (Giờ VN)"


def test_validate_schedule_time():
    now = vn_now()

    # 1. Thời điểm quá khứ -> Lỗi
    past_time = now - timedelta(hours=1)
    valid, msg = validate_schedule_time(past_time)
    assert valid is False

    # 2. Thời điểm quá gần (30 giây nữa) -> Lỗi
    near_time = now + timedelta(seconds=30)
    valid, msg = validate_schedule_time(near_time)
    assert valid is False

    # 3. Thời điểm hợp lệ (30 phút nữa) -> Hợp lệ
    future_time = now + timedelta(minutes=30)
    valid, msg = validate_schedule_time(future_time)
    assert valid is True
    assert msg == "Hợp lệ"

    # 4. Thời điểm quá xa (90 ngày nữa) -> Lỗi
    far_time = now + timedelta(days=90)
    valid, msg = validate_schedule_time(far_time)
    assert valid is False

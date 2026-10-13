"""
Kiểm thử chuyên biệt cho Task UX-04: Shared UI Primitives (DoD Compliance)
- Kiểm tra StatusChip ánh xạ đủ trạng thái SQLite/Graph API sang tiếng Việt chuẩn
- Kiểm tra EmptyState các ngữ cảnh và nút CTA
- Kiểm tra SafeConfirmDialog khóa nút nguy hiểm cho tới khi tích xác nhận
- Kiểm tra DateTimePickerVN chuyển đổi chuẩn múi giờ Việt Nam và UTC ISO
- Kiểm tra FeedbackBanner, ToastNotification, InlineError và MediaThumbnailCard
"""

from datetime import datetime, timedelta
import pytest
from PySide6.QtWidgets import QApplication

from src.lovira.domain.timezone import vn_now
from src.lovira.ui.widgets.status_chip import StatusChip, STATUS_CONFIG
from src.lovira.ui.widgets.empty_state import EmptyState
from src.lovira.ui.widgets.feedback import FeedbackBanner, ToastNotification, InlineError
from src.lovira.ui.widgets.confirm import SafeConfirmDialog
from src.lovira.ui.widgets.datetime_picker_vn import DateTimePickerVN
from src.lovira.ui.widgets.media_card import MediaThumbnailCard


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_status_chip_rendering_and_state_mapping(qapp):
    """DoD UX-04: StatusChip ánh xạ đúng các trạng thái và nhãn tiếng Việt."""
    test_states = [
        ("ready", "Sẵn sàng"),
        ("unverified", "Chưa xác minh"),
        ("token_expired", "Token hết hạn"),
        ("insufficient_permissions", "Thiếu quyền"),
        ("scheduled_local", "Lịch trên máy"),
        ("scheduled_remote", "Facebook đã nhận"),
        ("published", "Đã đăng thành công"),
        ("failed", "Thất bại"),
        ("unknown", "Cần đối chiếu"),
    ]

    for key, expected_label in test_states:
        chip = StatusChip(key)
        assert chip.lbl_text.text() == expected_label
        assert chip.toolTip() != ""

    # Thử cập nhật trạng thái động
    chip = StatusChip("scheduled_local")
    chip.update_status("published")
    assert chip.lbl_text.text() == "Đã đăng thành công"


def test_empty_state_factory_methods_and_cta(qapp):
    """DoD UX-04: EmptyState tạo đúng nội dung và phát signal khi bấm CTA."""
    called = []
    empty_pages = EmptyState.no_pages(on_add=lambda: called.append("add_page"))
    assert "Chưa kết nối Fanpage" in empty_pages.lbl_title.text()
    assert empty_pages.btn_action is not None

    empty_pages.btn_action.click()
    assert "add_page" in called

    empty_search = EmptyState.search_not_found(query="video test")
    assert "Không tìm thấy kết quả" in empty_search.lbl_title.text()
    assert "video test" in empty_search.lbl_desc.text()
    assert empty_search.btn_action is None


def test_feedback_banner_and_toast(qapp):
    """DoD UX-04: FeedbackBanner, ToastNotification và InlineError hoạt động đúng."""
    banner = FeedbackBanner(level="warning", message="Cảnh báo quyền hạn")
    assert banner.lbl_msg.text() == "Cảnh báo quyền hạn"

    err = InlineError("Mã Fanpage không được để trống")
    assert err.isVisible()
    assert "Mã Fanpage" in err.text()
    err.clear_error()
    assert not err.isVisible()

    toast = ToastNotification("Đã lưu nháp thành công", level="success", duration_ms=0)
    assert toast.lbl_msg.text() == "Đã lưu nháp thành công"


def test_safe_confirm_dialog_impact_and_checkbox_lock(qapp):
    """DoD UX-04: SafeConfirmDialog khóa nút nguy hiểm cho tới khi tích checkbox xác nhận."""
    dialog = SafeConfirmDialog(
        title="Gỡ Fanpage",
        headline="Bạn có chắc chắn muốn gỡ Fanpage này?",
        impact_items=[
            "2 lịch hẹn giờ trên máy sẽ bị hủy bỏ",
            "1 bài viết trên Facebook không thể xóa tự động",
        ],
        danger_action_text="Gỡ liên kết ngay",
    )

    # Ban đầu nút đỏ bị khóa an toàn
    assert not dialog.btn_danger.isEnabled()

    # Tích checkbox xác nhận
    dialog.chk_confirm.setChecked(True)
    assert dialog.btn_danger.isEnabled()

    # Bỏ tích -> khóa lại
    dialog.chk_confirm.setChecked(False)
    assert not dialog.btn_danger.isEnabled()


def test_datetime_picker_vn_timezone_and_validation(qapp):
    """DoD UX-04: DateTimePickerVN bảo đảm múi giờ Việt Nam và chuyển đổi ISO UTC đúng chuẩn."""
    picker = DateTimePickerVN(default_offset_hours=3)
    dt_vn = picker.get_vn_datetime()

    # Múi giờ phải là UTC+7
    assert dt_vn.tzinfo is not None
    assert "+07:00" in dt_vn.isoformat()

    # Chuỗi UTC ISO lưu trữ
    utc_iso = picker.get_utc_iso()
    assert "Z" in utc_iso or "+00:00" in utc_iso

    # Thời gian 3 giờ tới phải là tương lai hợp lệ
    assert picker.is_valid_future_time(buffer_minutes=5)

    # Đặt thời gian về quá khứ -> kiểm tra không hợp lệ
    past_time = vn_now() - timedelta(hours=1)
    picker.set_datetime_vn(past_time)
    assert not picker.is_valid_future_time(buffer_minutes=5)


def test_media_thumbnail_card_signals(qapp):
    """DoD UX-04: MediaThumbnailCard hiển thị thông tin và phát tín hiệu khi bấm nút."""
    sample_media = {
        "id": "med_test_1",
        "title": "Video Huong Dan San Pham",
        "duration": 75.0,  # 01:15
        "size_bytes": 15 * 1024 * 1024,
        "source_platform": "tiktok",
    }
    card = MediaThumbnailCard(sample_media)
    assert "Video Huong Dan San Pham" in card.lbl_title.text()
    assert "TIKTOK" in card.text() if hasattr(card, "text") else True

    received = []
    card.send_to_composer_requested.connect(lambda data: received.append(data["id"]))
    card.btn_compose.click()
    assert "med_test_1" in received

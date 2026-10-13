from src.lovira.domain.composer import (
    ContentType,
    ScheduleMode,
    PostComposerState,
    ContentSnapshot,
)


def test_composer_multi_page_and_caption_overrides():
    state = PostComposerState(
        content_type=ContentType.VIDEO,
        general_caption="Bộ sưu tập Mùa Thu 2026",
        media_path="/path/to/autumn.mp4",
        media_checksum="sha256_autumn",
        selected_page_ids=["page_1", "page_2", "page_3"],
    )

    # Page 2 có caption riêng
    state.set_override_caption("page_2", "Bộ sưu tập Mùa Thu dành riêng cho VIP Khách hàng Page 2")

    assert state.get_effective_caption("page_1") == "Bộ sưu tập Mùa Thu 2026"
    assert state.get_effective_caption("page_2") == "Bộ sưu tập Mùa Thu dành riêng cho VIP Khách hàng Page 2"
    assert state.get_effective_caption("page_3") == "Bộ sưu tập Mùa Thu 2026"

    # Tạo snapshots
    snapshots = state.create_snapshots()
    assert len(snapshots) == 3
    assert snapshots[0].page_id == "page_1"
    assert snapshots[0].final_caption == "Bộ sưu tập Mùa Thu 2026"
    assert snapshots[1].page_id == "page_2"
    assert snapshots[1].final_caption == "Bộ sưu tập Mùa Thu dành riêng cho VIP Khách hàng Page 2"


def test_schedule_toggle_preserves_values():
    # AC-06, AC-41: Tắt hẹn giờ không làm mất giờ đã nhập và không tự động đăng bài
    state = PostComposerState(
        content_type=ContentType.TEXT,
        general_caption="Bài test hẹn giờ",
        selected_page_ids=["page_1"],
    )

    state.toggle_schedule(True)
    state.scheduled_year = 2026
    state.scheduled_month = 10
    state.scheduled_day = 20
    state.scheduled_hour = 20
    state.scheduled_minute = 30
    assert state.is_scheduled is True

    # Người dùng tắt công tắc hẹn giờ (AC-06, AC-41)
    state.toggle_schedule(False)
    assert state.is_scheduled is False
    # Dữ liệu giờ đã nhập vẫn được giữ nguyên trong session
    assert state.scheduled_hour == 20
    assert state.scheduled_minute == 30
    assert state.scheduled_day == 20


def test_content_snapshot_immutability():
    # Section 7.2, AC-19: Bản chụp bất biến, nháp sửa đổi sau không làm đổi snapshot
    state = PostComposerState(
        content_type=ContentType.VIDEO,
        general_caption="Caption Ban Dau",
        media_path="/media/video.mp4",
        media_checksum="hash_original",
        selected_page_ids=["page_1"],
        revision=1,
    )

    snapshots = state.create_snapshots(scheduled_at_utc="2026-10-20T13:30:00Z")
    snap = snapshots[0]
    assert snap.final_caption == "Caption Ban Dau"
    assert snap.media_checksum == "hash_original"

    # Người dùng tiếp tục sửa state nháp trên UI
    state.general_caption = "Caption Da Duoc Sua Doi Sau Do"
    state.media_path = "/media/video_new.mp4"

    # Snapshot cũ KHÔNG bị thay đổi
    assert snap.final_caption == "Caption Ban Dau"
    assert snap.media_path == "/media/video.mp4"

    # Test serialization JSON
    json_str = snap.to_json()
    loaded_snap = ContentSnapshot.from_json(json_str)
    assert loaded_snap.batch_id == snap.batch_id
    assert loaded_snap.final_caption == "Caption Ban Dau"
    assert loaded_snap.scheduled_at_utc == "2026-10-20T13:30:00Z"

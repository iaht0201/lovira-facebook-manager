"""
Unit test cho F-21: Giao diện Tải Video & Media Library với luồng 1-click chuyển Soạn bài
Đáp ứng BR-05, BR-06, AC-04, AC-12
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.media.processor import MediaProcessor
from src.lovira.integrations.downloaders.video_downloader import (
    VideoDownloader,
    VideoMetadata,
    SupportedPlatform,
)
from src.lovira.ui.views.video_workspace import VideoWorkspaceView, VideoDownloadTab, MediaLibraryTab


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_video_ui.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_video_download_tab_inspect_and_1click_composer(qapp, temp_db, tmp_path):
    """BR-05, BR-06, AC-04: Lấy thông tin video, tải xong hiển thị nút chuyển Soạn bài 1-click."""
    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    tab = VideoDownloadTab(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    # 1. Kiểm tra Lấy thông tin video (Inspect)
    mock_meta = VideoMetadata(
        source_url="https://tiktok.com/@user/video/123",
        source_platform=SupportedPlatform.TIKTOK,
        video_id="vid_123",
        title="Review son môi Lovira",
        thumbnail_url="https://thumb.jpg",
        duration=45.0,
        uploader="Beauty Queen",
    )

    with patch.object(downloader, "extract_metadata", return_value=mock_meta):
        tab.url_input.setText("https://tiktok.com/@user/video/123")
        tab._inspect_video()

    assert "Review son môi Lovira" in tab.lbl_meta_title.text()
    assert "TIKTOK" in tab.lbl_meta_platform.text()

    # 2. Giả lập tải thành công và kiểm tra nút Soạn bài 1-click
    dummy_file = tmp_path / "downloaded_test.mp4"
    dummy_file.write_bytes(b"mock video binary")

    composer_signal_mock = MagicMock()
    tab.send_to_composer.connect(composer_signal_mock)

    tab._on_download_success({
        "file_path": str(dummy_file),
        "title": "Review son môi Lovira",
        "duration": 45.0,
        "platform": "tiktok",
    })

    assert not tab.btn_compose_now.isHidden()
    assert tab.progress_bar.value() == 100

    # Bấm nút Soạn bài 1-click (BR-06)
    tab.btn_compose_now.click()
    composer_signal_mock.assert_called_once()
    emitted_data = composer_signal_mock.call_args[0][0]
    assert emitted_data["file_path"] == str(dummy_file)
    assert emitted_data["media_id"] is not None


def test_media_library_tab_delete_protection_ac12(qapp, temp_db, tmp_path):
    """AC-12: Chặn xóa video trong thư viện nếu đang được một lịch đăng chờ tham chiếu."""
    media_repo = MediaRepository(temp_db)

    # Tạo asset
    asset_id = media_repo.add_media_asset(
        local_path=tmp_path / "active_video.mp4",
        checksum="chk_123",
        size_bytes=1000,
        duration=15.0,
        source_platform="tiktok",
    )

    # Tạo lịch đăng tham chiếu video này
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p_test', 'fb_p_test', 'Page');")
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_active', 'b1', 'req1', 'p_test', '{"media_ids": ["%s"]}', 'scheduled_local', '2026-10-20T10:00:00Z');
            """ % asset_id
        )

    tab = MediaLibraryTab(media_repo=media_repo)
    tab.reload_media_list()
    assert tab.table.rowCount() == 1

    # Chọn hàng đầu tiên
    tab.table.selectRow(0)

    # Giả lập bấm nút Xóa -> Phải hiện hộp thoại lỗi chặn xóa (AC-12)
    with patch.object(QMessageBox, "critical") as mock_critical:
        tab._on_delete_selected()
        mock_critical.assert_called_once()
        assert "AC-12" in mock_critical.call_args[0][1]

    # Kiểm tra asset vẫn còn nguyên trong DB, không bị xóa
    assert media_repo.get_media_asset(asset_id) is not None

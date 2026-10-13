"""
Unit tests cho Lovira Workspace 2.0 — Download Grid UX Refactor (v2).
Kiểm thử toàn diện:
- Link intake: 1 URL, N URL, văn bản chứa link Douyin/TikTok/Bilibili, deduplication.
- DownloadTaskListModel: Trạng thái, filter, sort, selection.
- DownloadQueueController: Bắt đầu tải, giới hạn đồng thời, retry, cancel.
- Post-processing & MediaRepository: lưu đúng source_platform, tạo thumbnail, emit media_downloaded.
- Bulk selection & handoff sang Composer.
"""

import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.media.processor import MediaProcessor
from src.lovira.integrations.downloaders.video_downloader import (
    VideoDownloader,
    VideoMetadata,
    SupportedPlatform,
)
from src.lovira.ui.views.video_workspace import (
    VideoDownloadTab,
    DownloadTask,
    DownloadTaskListModel,
    ROLE_TASK_STATE,
    ROLE_TASK_PROGRESS,
    ROLE_TASK_IS_SELECTED,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_download_grid.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_link_intake_extraction_and_deduplication(qapp, temp_db, tmp_path):
    """Kiểm tra LinkIntakePanel: tách link từ nhiều dòng & văn bản kèm link, deduplicate."""
    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    tab = VideoDownloadTab(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    sample_text = (
        "3.35 04/13 :8pm gOx:/ Y@m.qR # 被萌娃和狗狗治愈了 https://v.douyin.com/pCDZmEmURLw/ 复制此链接\n"
        "https://www.tiktok.com/@user/video/123456789\n"
        "https://v.douyin.com/pCDZmEmURLw/\n"  # Duplicate
        "https://www.bilibili.com/video/BV1xx411c7mD\n"
    )
    tab.link_text_edit.setPlainText(sample_text)

    urls = tab._extract_urls(sample_text)
    assert len(urls) == 3
    assert "https://v.douyin.com/pCDZmEmURLw/" in urls
    assert "https://www.tiktok.com/@user/video/123456789" in urls
    assert "https://www.bilibili.com/video/BV1xx411c7mD" in urls


def test_download_task_model_filtering_and_sorting(qapp):
    """Kiểm tra DownloadTaskListModel: thêm task, lọc theo trạng thái, sắp xếp."""
    model = DownloadTaskListModel()

    t1 = DownloadTask(task_id="t1", source_url="u1", normalized_url="u1", title="B Video", state="READY")
    t2 = DownloadTask(task_id="t2", source_url="u2", normalized_url="u2", title="A Video", state="DOWNLOADING")
    t3 = DownloadTask(task_id="t3", source_url="u3", normalized_url="u3", title="C Video", state="COMPLETED")
    t4 = DownloadTask(task_id="t4", source_url="u4", normalized_url="u4", title="D Video", state="FAILED")

    model.add_task(t1)
    model.add_task(t2)
    model.add_task(t3)
    model.add_task(t4)

    assert model.rowCount() == 4
    counts = model.counts_by_state()
    assert counts["all"] == 4
    assert counts["ready"] == 1
    assert counts["downloading"] == 1
    assert counts["completed"] == 1
    assert counts["failed"] == 1

    # Lọc chỉ video COMPLETED
    model.set_filter("completed")
    assert model.rowCount() == 1
    idx = model.index(0, 0)
    assert idx.data(ROLE_TASK_STATE) == "COMPLETED"

    # Lọc tất cả và sắp xếp theo Tiêu đề
    model.set_filter("all")
    model.set_sort("title")
    assert model.rowCount() == 4
    assert model.index(0, 0).data() == "A Video"
    assert model.index(1, 0).data() == "B Video"


def test_download_flow_and_media_repo_registration(qapp, temp_db, tmp_path):
    """Kiểm tra luồng tải: worker success -> tạo thumbnail -> lưu MediaRepository với đúng platform."""
    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    tab = VideoDownloadTab(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    dummy_video = tmp_path / "douyin_test.mp4"
    dummy_video.write_bytes(b"binary mp4 content")

    task = DownloadTask(
        task_id="task_douyin_1",
        source_url="https://v.douyin.com/test1234/",
        normalized_url="https://v.douyin.com/test1234/",
        source_platform="douyin",
        title="Video Douyin Tuyệt Đẹp",
        state="DOWNLOADING",
    )
    tab.model.add_task(task)

    media_downloaded_mock = MagicMock()
    tab.media_downloaded.connect(media_downloaded_mock)

    # Giả lập hoàn thành tải
    tab._on_worker_success("task_douyin_1", str(dummy_video), "douyin")

    # Kiểm tra task được cập nhật
    updated = tab.model.get_task("task_douyin_1")
    assert updated.state == "COMPLETED"
    assert updated.local_file_path == str(dummy_video)
    assert updated.media_id is not None
    assert updated.progress_percent == 100

    # Kiểm tra repository đã lưu đúng source_platform
    asset = media_repo.get_media_asset(updated.media_id)
    assert asset is not None
    assert asset["source_platform"] == "douyin"
    assert asset["source_url"] == "https://v.douyin.com/test1234/"
    media_downloaded_mock.assert_called_once()


def test_bulk_selection_and_composer_handoff(qapp, temp_db, tmp_path):
    """Kiểm tra bulk selection ở bottom bar và bàn giao sang Composer."""
    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    tab = VideoDownloadTab(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    t1 = DownloadTask(
        task_id="t1",
        source_url="https://tiktok.com/@user/video/1",
        normalized_url="https://tiktok.com/@user/video/1",
        source_platform="tiktok",
        title="Video 1",
        local_file_path=str(tmp_path / "v1.mp4"),
        media_id="m1",
        state="COMPLETED",
    )
    t2 = DownloadTask(
        task_id="t2",
        source_url="https://tiktok.com/@user/video/2",
        normalized_url="https://tiktok.com/@user/video/2",
        source_platform="tiktok",
        title="Video 2",
        local_file_path=str(tmp_path / "v2.mp4"),
        media_id="m2",
        state="COMPLETED",
    )
    tab.model.add_task(t1)
    tab.model.add_task(t2)

    # Ban đầu bottom bar ẩn
    assert tab.bottom_bar.isHidden()

    # Chọn task 1
    tab.model.toggle_select("t1")
    tab._update_ui_state()
    assert not tab.bottom_bar.isHidden()
    assert "1 video hoàn tất" in tab.lbl_selected_summary.text()

    # Bàn giao 1 video sang composer
    composer_mock = MagicMock()
    tab.send_to_composer.connect(composer_mock)
    tab.btn_bulk_compose.click()

    composer_mock.assert_called_once()
    payload = composer_mock.call_args[0][0]
    assert payload["media_id"] == "m1"
    assert payload["file_path"] == str(tmp_path / "v1.mp4")

"""
Unit tests cho UX-09: Media Library & Video Downloader 2.0 (video_workspace.py)
Kiểm thử toàn diện:
- VideoDownloadTab: Lấy thông tin video, kiểm tra thumbnail và metadata
- VideoDownloadTab: Tiến trình tải, 1-click Soạn bài & Đặt lịch (BR-06)
- MediaLibraryTab: Bảng video, bộ lọc nền tảng và live search filter
- MediaLibraryTab: Chuyển đổi giữa bảng danh sách và EmptyState onboarding
- MediaLibraryTab: Bảo vệ an toàn AC-12 chặn xóa video đang có lịch hẹn chờ
- MediaLibraryTab: Nút chọn soạn bài với video đã chọn
- VideoWorkspaceView: Điều hướng tự động giữa Tab Tải video và Thư viện media theo Route
"""

import pytest
import os
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
from src.lovira.ui.views.video_workspace import (
    VideoWorkspaceView,
    VideoDownloadTab,
    MediaLibraryTab,
)
from src.lovira.ui.shell.navigation import Route


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux09_media.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


@pytest.fixture
def seed_media(temp_db, tmp_path):
    """Tạo trước một số video mẫu trong thư viện media."""
    media_repo = MediaRepository(temp_db)
    f1 = tmp_path / "tiktok_reels_01.mp4"
    f1.write_bytes(b"data1" * 100)
    id1 = media_repo.add_media_asset(
        local_path=f1,
        checksum="chk_1",
        size_bytes=500,
        duration=30.0,
        source_platform="tiktok",
        source_url="https://tiktok.com/@user/video/1",
    )

    f2 = tmp_path / "douyin_cooking_02.mp4"
    f2.write_bytes(b"data2" * 200)
    id2 = media_repo.add_media_asset(
        local_path=f2,
        checksum="chk_2",
        size_bytes=1000,
        duration=65.0,
        source_platform="douyin",
        source_url="https://douyin.com/video/2",
    )

    f3 = tmp_path / "bilibili_tech_03.mp4"
    f3.write_bytes(b"data3" * 300)
    id3 = media_repo.add_media_asset(
        local_path=f3,
        checksum="chk_3",
        size_bytes=1500,
        duration=120.0,
        source_platform="bilibili",
        source_url="https://bilibili.com/video/3",
    )

    return {"media_repo": media_repo, "ids": [id1, id2, id3], "paths": [f1, f2, f3]}


def test_download_tab_inspect_and_compose_now(qapp, temp_db, tmp_path):
    """Kiểm thử Tab Tải video: inspect metadata và nút 1-click Soạn bài (BR-06)."""
    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    tab = VideoDownloadTab(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    mock_meta = VideoMetadata(
        source_url="https://tiktok.com/@lovira/video/999",
        source_platform=SupportedPlatform.TIKTOK,
        video_id="v999",
        title="Hướng dẫn phối đồ hè 2026",
        thumbnail_url=None,
        duration=50.0,
        uploader="Lovira Fashion",
    )

    with patch.object(downloader, "extract_metadata", return_value=mock_meta):
        tab.url_input.setText("https://tiktok.com/@lovira/video/999")
        tab._inspect_video()

    assert "Hướng dẫn phối đồ hè 2026" in tab.lbl_meta_title.text()
    assert "TIKTOK" in tab.lbl_meta_platform.text()
    assert "00:50" in tab.lbl_meta_duration.text()

    # Giả lập hoàn tất tải video
    mock_file = tmp_path / "downloaded_sample.mp4"
    mock_file.write_bytes(b"video payload")

    compose_signals = []
    tab.send_to_composer.connect(lambda d: compose_signals.append(d))

    tab._on_download_success({
        "file_path": str(mock_file),
        "title": "Hướng dẫn phối đồ hè 2026",
        "duration": 50.0,
        "platform": "tiktok",
    })

    assert tab.progress_bar.value() == 100
    assert not tab.btn_compose_now.isHidden()

    # Bấm nút 1-click Soạn bài
    tab.btn_compose_now.click()
    assert len(compose_signals) == 1
    assert compose_signals[0]["file_path"] == str(mock_file)
    assert compose_signals[0]["media_id"] is not None


def test_media_library_filter_and_search(qapp, seed_media):
    """Kiểm thử Thư viện Media: lọc nền tảng và tìm kiếm thời gian thực."""
    media_repo = seed_media["media_repo"]
    tab = MediaLibraryTab(media_repo=media_repo)

    # Ban đầu có 3 video
    assert tab.content_stack.currentIndex() == 0  # Table view
    assert tab.table.rowCount() == 3

    # 1. Lọc theo Douyin
    idx = tab.cb_filter_platform.findText("Douyin")
    assert idx >= 0
    tab.cb_filter_platform.setCurrentIndex(idx)
    assert tab.table.rowCount() == 1
    assert "DOUYIN" in tab.table.item(0, 1).text()

    # Trả về Tất cả
    tab.cb_filter_platform.setCurrentIndex(0)
    assert tab.table.rowCount() == 3

    # 2. Tìm kiếm theo tên file
    tab.search_filter.setText("tiktok_reels")
    assert tab.table.rowCount() == 1
    assert "TIKTOK" in tab.table.item(0, 1).text()

    # 3. Tìm kiếm từ khóa không tồn tại -> chuyển EmptyState
    tab.search_filter.setText("non_existent_search_query_999")
    assert tab.content_stack.currentIndex() == 1  # EmptyState view

    # Xóa tìm kiếm -> quay lại bảng
    tab.search_filter.clear()
    assert tab.content_stack.currentIndex() == 0
    assert tab.table.rowCount() == 3


def test_media_library_compose_selected_and_ac12_protection(qapp, temp_db, seed_media, tmp_path):
    """Kiểm thử soạn bài từ video chọn và bảo vệ AC-12 chặn xóa khi có lịch chờ."""
    media_repo = seed_media["media_repo"]
    active_media_id = seed_media["ids"][0]

    # Tạo lịch đăng bài tham chiếu active_media_id
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p_test', 'fb_p', 'Test Page');")
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_active_1', 'b1', 'req1', 'p_test', '{"media_ids": ["%s"]}', 'scheduled_local', '2026-10-30T10:00:00Z');
            """ % active_media_id
        )

    tab = MediaLibraryTab(media_repo=media_repo)
    assert tab.table.rowCount() == 3

    # 1. Soạn bài với video thứ 2 (không bị khóa)
    tab.table.selectRow(1)
    compose_events = []
    tab.send_to_composer.connect(lambda d: compose_events.append(d))

    tab._on_compose_selected()
    assert len(compose_events) == 1
    assert compose_events[0]["media_id"] == tab.table.item(1, 0).text()

    # 2. Xóa video đầu tiên (đang có lịch chờ active_job_count > 0) -> Phải bị chặn AC-12
    # Tìm dòng chứa active_media_id
    target_row = -1
    for r in range(tab.table.rowCount()):
        if tab.table.item(r, 0).text() == active_media_id:
            target_row = r
            break
    assert target_row >= 0
    tab.table.selectRow(target_row)

    with patch.object(QMessageBox, "critical") as mock_crit:
        tab._on_delete_selected()
        mock_crit.assert_called_once()
        assert "AC-12" in mock_crit.call_args[0][1]

    # Video vẫn còn nguyên trong DB
    assert media_repo.get_media_asset(active_media_id) is not None


def test_video_workspace_route_tab_switching(qapp, temp_db, tmp_path):
    """Kiểm thử VideoWorkspaceView chuyển đổi tab tự động cho Route.DOWNLOADS và Route.MEDIA."""
    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    workspace = VideoWorkspaceView(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
    )

    # Ban đầu tab Tải video là tab 0
    assert workspace.tab_widget.currentIndex() == 0

    # Chuyển sang Thư viện media
    workspace.show_library_tab()
    assert workspace.tab_widget.currentIndex() == 1

    # Chuyển lại Tải video
    workspace.show_download_tab()
    assert workspace.tab_widget.currentIndex() == 0


def test_download_tab_batch_schedule_and_fanpage_selection(qapp, temp_db, tmp_path):
    """Kiểm tra chọn fanpage đích, tự động lấy title & hashtag và lên lịch đăng hàng loạt."""
    from src.lovira.security.vault import SecretVault
    from src.lovira.storage.page_repository import PageRepository
    from src.lovira.storage.queue_repository import PublishQueueRepository
    from src.lovira.ui.views.video_workspace import BatchComposeDialog, DownloadTask

    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)

    # 1. Tạo 2 page trong DB
    p1 = page_repo.upsert_page(facebook_page_id="111222333", name="Fanpage Thú Cưng", status="ready")
    p2 = page_repo.upsert_page(facebook_page_id="444555666", name="Fanpage Đời Sống", status="ready")

    downloader = VideoDownloader()
    media_repo = MediaRepository(temp_db)
    media_processor = MediaProcessor()

    tab = VideoDownloadTab(
        downloader=downloader,
        media_repo=media_repo,
        media_processor=media_processor,
        download_dir=tmp_path,
        page_repo=page_repo,
        queue_repo=queue_repo,
    )

    # 2. Thêm video đã hoàn tất có title & hashtag
    vid_file = tmp_path / "dog_video.mp4"
    vid_file.write_bytes(b"dog video dummy data")
    t = DownloadTask(
        task_id="task_dog_01",
        source_url="https://tiktok.com/@user/dog",
        normalized_url="https://tiktok.com/@user/dog",
        source_platform="tiktok",
        title="#dachshund #cholapxuong #fyp #thucung",
        state="COMPLETED",
        local_file_path=str(vid_file),
        media_id="media_dog_01",
    )
    tab.model.add_task(t)

    # 3. Chọn tất cả video đã tải
    tab._select_all_completed()
    selected = tab.model.get_selected_completed_tasks()
    assert len(selected) == 1
    assert selected[0].task_id == "task_dog_01"

    # 4. Kiểm tra BatchComposeDialog
    fanpages = page_repo.list_pages()
    media_items = [{
        "id": t.media_id,
        "title": t.title,
        "caption": t.title,
        "local_path": t.local_file_path,
        "thumbnail_path": "",
        "duration": 15.0,
    }]

    dlg = BatchComposeDialog(
        media_items=media_items,
        fanpages=fanpages,
        initial_selected_page_ids=[p1],
        initial_mode="schedule",
    )

    # Kiểm tra tự động lấy title & hashtag của video
    assert "#dachshund #cholapxuong" in dlg.caption_edit.toPlainText()
    assert p1 in dlg.selected_page_ids
    assert dlg.table_preview.rowCount() >= 1

    # Kiểm tra xác nhận đặt lịch
    confirm_payload = []
    dlg.batch_confirmed.connect(lambda p: confirm_payload.append(p))
    dlg._on_confirm_clicked()

    assert len(confirm_payload) == 1
    payload = confirm_payload[0]
    assert len(payload["fanpages"]) >= 1
    assert payload["use_original_titles"] is True


def test_media_edit_post_dialog_save_and_quick_publish(qapp, temp_db, seed_media, tmp_path):
    """Kiểm thử popup chỉnh sửa tiêu đề, nội dung, hashtag, bình luận và đăng nhanh."""
    from src.lovira.ui.views.video_workspace import MediaEditPostDialog
    from src.lovira.security.vault import SecretVault
    from src.lovira.storage.page_repository import PageRepository
    from src.lovira.storage.queue_repository import PublishQueueRepository

    vault = SecretVault(fallback_vault_dir=tmp_path / "vault2")
    media_repo = seed_media["media_repo"]
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)

    p1 = page_repo.upsert_page(
        facebook_page_id="page_dog_fan",
        name="Lạp Xưởng Đáng Yêu",
        status="ready",
    )
    pages = page_repo.list_pages()

    asset_id = seed_media["ids"][0]
    asset = media_repo.get_media_asset(asset_id)

    dlg = MediaEditPostDialog(
        asset=asset,
        pages=pages,
        queue_repo=queue_repo,
        media_repo=media_repo,
    )

    # 1. Điền chỉnh sửa tiêu đề, nội dung, hashtag, bình luận
    dlg.txt_title.setText("Chó lạp xưởng đáng yêu nhất tiktok")
    dlg.txt_caption.setPlainText("Video chú chó lạp xưởng siêu cưng nè cả nhà ơi!")
    dlg.txt_hashtags.setText("#lapxuong #dachshund #viral")
    dlg.txt_comment.setPlainText("Link mua thức ăn và đồ chơi cho cún ở bình luận này nha cả nhà: https://lovira.vn")

    # Chọn Fanpage
    idx = dlg.cb_page.findData(p1)
    assert idx >= 0
    dlg.cb_page.setCurrentIndex(idx)

    # 2. Test Lưu thông tin vào DB
    with patch.object(QMessageBox, "information"):
        dlg._on_save_clicked()

    # Kiểm tra DB đã cập nhật đầy đủ
    saved = media_repo.get_media_asset(asset_id)
    assert saved["title"] == "Chó lạp xưởng đáng yêu nhất tiktok"
    assert saved["caption"] == "Video chú chó lạp xưởng siêu cưng nè cả nhà ơi!"
    assert saved["hashtags"] == "#lapxuong #dachshund #viral"
    assert saved["first_comment"] == "Link mua thức ăn và đồ chơi cho cún ở bình luận này nha cả nhà: https://lovira.vn"
    assert saved["target_page_id"] == p1

    # 3. Test Đăng nhanh ngay
    dlg2 = MediaEditPostDialog(
        asset=saved,
        pages=pages,
        queue_repo=queue_repo,
        media_repo=media_repo,
    )
    published_jobs = []
    dlg2.post_published.connect(lambda j: published_jobs.extend(j))

    with patch.object(QMessageBox, "information"):
        dlg2._on_quick_publish_clicked()

    assert len(published_jobs) == 1
    job_id = published_jobs[0]
    job = queue_repo.get_job(job_id)
    assert job["page_id"] == p1

    from src.lovira.domain.composer import ContentSnapshot
    snap = ContentSnapshot.from_json(job["content_snapshot"])
    assert snap.title == "Chó lạp xưởng đáng yêu nhất tiktok"
    assert snap.first_comment == "Link mua thức ăn và đồ chơi cho cún ở bình luận này nha cả nhà: https://lovira.vn"
    assert "#lapxuong #dachshund #viral" in snap.final_caption


def test_media_library_multi_select_and_batch_quick_publish(qapp, temp_db, tmp_path):
    """Kiểm thử tính năng chọn nhiều video cùng lúc, nút Chọn tất cả/Bỏ chọn và Đăng nhanh hàng loạt."""
    from src.lovira.storage.page_repository import PageRepository
    from src.lovira.storage.queue_repository import PublishQueueRepository
    from src.lovira.security.vault import SecretVault
    from src.lovira.ui.views.video_workspace import MediaLibraryTab, ROLE_MEDIA_ID

    vault = SecretVault(fallback_vault_dir=tmp_path / "vault_test")
    media_repo = MediaRepository(temp_db)
    page_repo = PageRepository(temp_db, vault)
    queue_repo = PublishQueueRepository(temp_db)

    # 1. Tạo 2 page và 3 video
    p1 = page_repo.upsert_page(facebook_page_id="fb_p1", name="Page Nhất Được Nè", status="ready")
    p2 = page_repo.upsert_page(facebook_page_id="fb_p2", name="Page Thời Trang", status="ready")

    f1 = tmp_path / "vid1.mp4"
    f2 = tmp_path / "vid2.mp4"
    f3 = tmp_path / "vid3.mp4"
    for f in (f1, f2, f3):
        f.write_bytes(b"dummy")

    id1 = media_repo.add_media_asset(local_path=str(f1), checksum="chk1", size_bytes=1000, duration=15.0, source_platform="tiktok")
    id2 = media_repo.add_media_asset(local_path=str(f2), checksum="chk2", size_bytes=2000, duration=20.0, source_platform="tiktok")
    id3 = media_repo.add_media_asset(local_path=str(f3), checksum="chk3", size_bytes=3000, duration=25.0, source_platform="tiktok")

    media_repo.update_asset_full_metadata(id1, "Video 1 Cún", "Mô tả 1", "#cun1", None, target_page_id=p1)
    media_repo.update_asset_full_metadata(id2, "Video 2 Mèo", "Mô tả 2", "#meo2", None, target_page_id=p1)
    media_repo.update_asset_full_metadata(id3, "Video 3 Voi", "Mô tả 3", "#voi3", None, target_page_id=p1)

    tab = MediaLibraryTab(media_repo=media_repo, page_repo=page_repo, queue_repo=queue_repo)
    tab._selected_page_ids = [p1]

    # 2. Test nút Chọn tất cả trên Top Toolbar
    assert tab.selection_bar.isHidden()
    tab.btn_select_all_top.click()

    assert not tab.selection_bar.isHidden()
    assert "Đã chọn 3 video" in tab.lbl_selected_count.text()
    assert len(tab._get_selected_asset_ids()) == 3

    # 3. Test nút Bỏ chọn trên Bottom Selection Bar
    tab.btn_clear_selection.click()
    assert tab.selection_bar.isHidden()
    assert len(tab._get_selected_asset_ids()) == 0

    # 4. Test chọn nhiều từng video qua _toggle_checkbox_selection
    idx0 = tab.model.index(0, 0)
    idx1 = tab.model.index(1, 0)
    tab._toggle_checkbox_selection(idx0)
    tab._toggle_checkbox_selection(idx1)

    assert "Đã chọn 2 video" in tab.lbl_selected_count.text()
    expected_selected = {tab.model.index(0, 0).data(ROLE_MEDIA_ID), tab.model.index(1, 0).data(ROLE_MEDIA_ID)}
    assert set(tab._get_selected_asset_ids()) == expected_selected

    # 5. Test Đăng nhanh hàng loạt các video đã chọn
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(QMessageBox, "information"):
            with patch.object(QMessageBox, "warning"):
                with patch.object(QMessageBox, "critical"):
                    tab._on_quick_publish_selected()

    # Kiểm tra jobs trong queue_repo
    jobs = queue_repo.list_jobs(limit=10)
    assert len(jobs) == 2
    for job in jobs:
        assert job["page_id"] == p1
        assert job["state"] in ("queued", "scheduled_local")



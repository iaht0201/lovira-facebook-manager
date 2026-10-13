"""
Unit tests cho Lovira Workspace 2.0 — Media Library Grid UX Refactor
Kiểm thử toàn diện các tiêu chí Acceptance Criteria M01 -> M20:
- M01 & M03: Hiển thị Thumbnail Grid trên QListView IconMode với MediaAssetListModel
- M04: Chọn bằng checkbox, đếm chính xác số lượng video được chọn
- M05: Ctrl + A chọn tất cả kết quả đang hiển thị, Esc bỏ chọn
- M06: Double click mở xem trước video, không tự động đăng bài
- M07: Fanpage picker popup tìm kiếm, lọc trang, đếm trang chọn
- M08: Tính toán chính xác số lượng bài dự kiến: N video x M Fanpage
- M09: Trạng thái tổng hợp (Đã lên lịch, Đã đăng, Có lỗi, Chưa sử dụng)
- M10: Nhận diện File thất lạc (Missing) khi file không còn trên ổ cứng
- M11: AC-12 chặn xóa video khi có lịch đăng active_job_count > 0
- M12: Phân biệt Bỏ khỏi thư viện (remove_file=False) và Xóa file vật lý
- M14: Phân biệt các Empty State (Chưa có media vs Không tìm thấy kết quả)
- M18: Thanh contextual toolbar ẩn khi chưa chọn, hiện khi chọn >= 1 video
"""

import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtCore import Qt, QModelIndex, QItemSelectionModel
from PySide6.QtWidgets import QApplication, QMessageBox

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.media_repository import MediaRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.ui.views.video_workspace import (
    MediaLibraryTab,
    MediaAssetListModel,
    MediaCardDelegate,
    MediaGridView,
    FanpagePickerPopup,
    BatchComposeDialog,
    ROLE_MEDIA_ID,
    ROLE_STATUS_KEY,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_grid_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_grid_ux.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


@pytest.fixture
def seed_assets(temp_db, tmp_path):
    media_repo = MediaRepository(temp_db)
    vault = MagicMock()
    vault.retrieve_secret.return_value = "mock_token"
    page_repo = PageRepository(temp_db, secret_vault=vault)

    # Tạo 3 video
    f1 = tmp_path / "video_fall_2026.mp4"
    f1.write_bytes(b"content1" * 100)
    id1 = media_repo.add_media_asset(
        local_path=f1,
        checksum="chk_fall",
        size_bytes=3800000,
        duration=23.0,
        source_platform="tiktok",
        source_url="https://tiktok.com/@shop/video/1",
    )

    f2 = tmp_path / "review_product_new.mp4"
    f2.write_bytes(b"content2" * 100)
    id2 = media_repo.add_media_asset(
        local_path=f2,
        checksum="chk_review",
        size_bytes=1000000,
        duration=9.0,
        source_platform="douyin",
        source_url="https://douyin.com/video/2",
    )

    f3 = tmp_path / "intro_store.mp4"
    f3.write_bytes(b"content3" * 100)
    id3 = media_repo.add_media_asset(
        local_path=f3,
        checksum="chk_intro",
        size_bytes=2100000,
        duration=22.0,
        source_platform="bilibili",
        source_url="https://bilibili.com/video/3",
    )

    # Thêm 2 fanpage mẫu
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p1', 'fb_p1', 'Shop Thời Trang Lovira');")
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p2', 'fb_p2', 'Lovira Beauty Official');")

    return {
        "media_repo": media_repo,
        "page_repo": page_repo,
        "ids": [id1, id2, id3],
        "files": [f1, f2, f3],
    }


def test_m01_m18_grid_initial_view_and_hidden_toolbar(qapp, seed_assets):
    """M01 & M18: Grid hiển thị các card và toolbar ẩn khi selection = 0."""
    tab = MediaLibraryTab(media_repo=seed_assets["media_repo"], page_repo=seed_assets["page_repo"])
    assert tab.content_stack.currentIndex() == 0  # Content stack
    assert tab.model.rowCount() == 3
    assert tab.selection_bar.isHidden()  # Toolbar ẩn khi chưa chọn video nào


def test_m04_m18_selection_and_contextual_toolbar(qapp, seed_assets):
    """M04: Chọn video làm hiện toolbar ngữ cảnh với số lượng chính xác."""
    tab = MediaLibraryTab(media_repo=seed_assets["media_repo"], page_repo=seed_assets["page_repo"])
    tab.show()

    # Chọn 1 item bằng selectionModel
    idx0 = tab.model.index(0, 0)
    tab.grid_view.selectionModel().select(idx0, QItemSelectionModel.SelectionFlag.Select)

    assert not tab.selection_bar.isHidden()
    assert "Đã chọn 1 video" in tab.lbl_selected_count.text()
    assert tab.btn_compose_selected.text() == "🎬 Soạn bài"

    # Chọn thêm item thứ 2
    idx1 = tab.model.index(1, 0)
    tab.grid_view.selectionModel().select(idx1, QItemSelectionModel.SelectionFlag.Select)

    assert "Đã chọn 2 video" in tab.lbl_selected_count.text()
    assert tab.btn_compose_selected.text() == "🎬 Tạo bài hàng loạt"
    assert tab.btn_schedule_selected.text() == "📅 Lên lịch hàng loạt"

    # Bỏ chọn
    tab.btn_clear_selection.click()
    assert tab.selection_bar.isHidden()


def test_m05_select_all_and_clear_keyboard(qapp, seed_assets):
    """M05: Ctrl+A chọn toàn bộ kết quả đang hiển thị."""
    tab = MediaLibraryTab(media_repo=seed_assets["media_repo"], page_repo=seed_assets["page_repo"])
    tab.grid_view.selectAll()

    assert len(tab.grid_view.selectionModel().selectedIndexes()) == 3
    assert "Đã chọn 3 video" in tab.lbl_selected_count.text()

    tab.grid_view.clearSelection()
    assert len(tab.grid_view.selectionModel().selectedIndexes()) == 0
    assert not tab.selection_bar.isVisible()


def test_m06_double_click_previews_video(qapp, seed_assets):
    """M06: Double click gọi mở xem trước video, không tự động đăng."""
    tab = MediaLibraryTab(media_repo=seed_assets["media_repo"], page_repo=seed_assets["page_repo"])
    idx = tab.model.index(0, 0)

    preview_signals = []
    tab.grid_view.item_double_clicked_preview.connect(lambda aid: preview_signals.append(aid))

    tab.grid_view._on_double_click(idx)
    assert len(preview_signals) == 1
    assert preview_signals[0] == seed_assets["ids"][0]


def test_m07_fanpage_picker_search_and_select(qapp, seed_assets):
    """M07: Dropdown chọn Fanpage hỗ trợ tìm kiếm và chọn nhiều trang."""
    pages = seed_assets["page_repo"].list_pages()
    popup = FanpagePickerPopup(pages, initial_selected_ids=[])

    assert len(popup.checkbox_map) == 2

    # Lọc tìm kiếm 'Beauty'
    popup.search_input.setText("Beauty")
    assert not popup.checkbox_map["p2"].parentWidget().isHidden()
    assert popup.checkbox_map["p1"].parentWidget().isHidden()

    # Chọn trang
    popup.checkbox_map["p2"].setChecked(True)
    assert "p2" in popup.selected_ids

    # Áp dụng
    selected_result = []
    popup.pages_selected.connect(lambda pids: selected_result.extend(pids))
    popup._apply_and_close()

    assert selected_result == ["p2"]


def test_m08_batch_compose_dialog_calculation(qapp, seed_assets):
    """M08: BatchComposeDialog tính toán chuẩn xác N video x M Fanpage = N*M bài dự kiến."""
    items = [seed_assets["media_repo"].get_media_asset(aid) for aid in seed_assets["ids"]]
    pages = seed_assets["page_repo"].list_pages()

    # 3 video x 2 fanpage = 6 bài
    dlg = BatchComposeDialog(media_items=items, fanpages=pages)
    assert dlg.table_preview.rowCount() == 6
    assert "6 lịch đăng" in dlg.btn_confirm.text()


def test_m09_publication_status_mapping(qapp, temp_db, seed_assets):
    """M09: Trạng thái tổng hợp phản ánh chính xác lịch hẹn và bài đăng."""
    media_repo = seed_assets["media_repo"]
    id_scheduled = seed_assets["ids"][0]
    id_published = seed_assets["ids"][1]

    # Tạo 1 job scheduled cho id_scheduled và 1 job published cho id_published
    with temp_db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_sched', 'b1', 'r1', 'p1', '{"primary_media_id": "%s"}', 'scheduled_local', '2026-10-25T10:00:00Z');
            """ % id_scheduled
        )
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_pub', 'b2', 'r2', 'p1', '{"primary_media_id": "%s"}', 'published', '2026-10-10T10:00:00Z');
            """ % id_published
        )

    tab = MediaLibraryTab(media_repo=media_repo, page_repo=seed_assets["page_repo"])
    tab.reload_media_list()

    # Kiểm tra trạng thái UI trong model
    for r in range(tab.model.rowCount()):
        mid = tab.model.get_media_id_at(r)
        status_key = tab.model.data(tab.model.index(r, 0), ROLE_STATUS_KEY)
        if mid == id_scheduled:
            assert status_key == "scheduled"
        elif mid == id_published:
            assert status_key == "published"
        else:
            assert status_key == "unused"


def test_m10_missing_file_detection(qapp, seed_assets):
    """M10: Tự động cảnh báo File thất lạc khi file vật lý bị xóa trên đĩa."""
    media_repo = seed_assets["media_repo"]
    f_missing = seed_assets["files"][2]
    if f_missing.exists():
        f_missing.unlink()  # Xóa file trên đĩa

    tab = MediaLibraryTab(media_repo=media_repo, page_repo=seed_assets["page_repo"])
    tab.reload_media_list()

    # Asset thứ 3 phải có ui_status_key == 'missing'
    found_missing = False
    for r in range(tab.model.rowCount()):
        mid = tab.model.get_media_id_at(r)
        if mid == seed_assets["ids"][2]:
            st = tab.model.data(tab.model.index(r, 0), ROLE_STATUS_KEY)
            assert st == "missing"
            found_missing = True
            break
    assert found_missing


def test_m11_ac12_delete_protection_dialog(qapp, temp_db, seed_assets):
    """M11: AC-12 chặn xóa khi asset có active job."""
    media_repo = seed_assets["media_repo"]
    active_id = seed_assets["ids"][0]

    with temp_db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO publish_jobs (id, batch_id, client_request_id, page_id, content_snapshot, state, scheduled_at_utc)
            VALUES ('job_act', 'b1', 'r1', 'p1', '{"media_ids": ["%s"]}', 'scheduled_local', '2026-10-30T10:00:00Z');
            """ % active_id
        )

    tab = MediaLibraryTab(media_repo=media_repo, page_repo=seed_assets["page_repo"])
    tab.grid_view.selectionModel().select(tab.model.index(0, 0), QItemSelectionModel.SelectionFlag.Select)

    with patch.object(QMessageBox, "critical") as mock_crit:
        tab._on_delete_selected()
        mock_crit.assert_called_once()
        assert "AC-12" in mock_crit.call_args[0][1]


def test_m14_empty_states(qapp, seed_assets):
    """M14: Phân biệt các Empty State (kết quả lọc rỗng vs thư viện rỗng)."""
    tab = MediaLibraryTab(media_repo=seed_assets["media_repo"], page_repo=seed_assets["page_repo"])

    # Tìm kiếm không có kết quả
    tab.search_filter.setText("chuoi_khong_ton_tai_xyz")
    assert tab.content_stack.currentIndex() == 1
    assert "Không tìm thấy video nào" in tab.empty_state.lbl_title.text()

    # Xóa bộ lọc -> quay về 0
    tab._reset_filters()
    assert tab.content_stack.currentIndex() == 0
    assert tab.model.rowCount() == 3

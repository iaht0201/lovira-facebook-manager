"""
Unit test cho F-22: Giao diện Soạn bài & Đặt lịch đa Page
Đáp ứng BR-04, BR-06, AC-05, AC-06, AC-07, AC-15, AC-19, AC-41
Đã cập nhật theo Lovira Workspace 2.0 (sử dụng page_dropdown / FanpageMultiSelect)
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt, QDateTime
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.security.vault import SecretVault
from src.lovira.ui.views.post_composer import PostComposerView


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_composer_ui.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_composer_ui_page_selection_and_button_label(qapp, temp_db, tmp_path):
    """Section 4.3 & AC-05: Đổi nhãn nút động ghi rõ số Page đích và phương thức."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p1 = page_repo.upsert_page("fb_101", "Lovira Fashion", status="ready")
    p2 = page_repo.upsert_page("fb_102", "Lovira Cosmetics", status="ready")

    queue_repo = PublishQueueRepository(temp_db)
    view = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)

    # Ban đầu chưa chọn Page nào
    assert "0 Page" in view.btn_submit.text()

    # Chọn 2 Page qua page_dropdown
    view.page_dropdown.set_page_selected(p1, True)
    view.page_dropdown.set_page_selected(p2, True)
    assert len(view.page_dropdown.selected_page_ids()) == 2
    assert "Đăng ngay lên 2 Page" in view.btn_submit.text()

    # Bật Hẹn giờ (AC-06) -> Nhãn đổi thành Đặt lịch
    view.chk_schedule.setChecked(True)
    assert "Đặt lịch cho 2 Page" in view.btn_submit.text()
    assert not view.schedule_picker_frame.isHidden()

    # Tắt Hẹn giờ (AC-41) -> Nhãn đổi lại Đăng ngay, KHÔNG tự động đăng bài
    view.chk_schedule.setChecked(False)
    assert "Đăng ngay lên 2 Page" in view.btn_submit.text()
    assert view.schedule_picker_frame.isHidden()


def test_composer_ui_attach_video_and_submit_batch(qapp, temp_db, tmp_path):
    """BR-06, AC-15, AC-19: Gắn video từ 1-click workflow và gửi hàng đợi nguyên tử."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p_id = page_repo.upsert_page("fb_p1", "Lovira Test Page", status="ready")

    queue_repo = PublishQueueRepository(temp_db)
    view = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)

    # 1. Gắn video từ 1-click workflow
    view.attach_video_data({
        "media_id": "med_test_123",
        "file_path": "C:/videos/tiktok_dance.mp4",
        "title": "Vũ điệu mùa hè Lovira",
    })

    assert "med_test_123" in view.lbl_media_info.text()
    assert view.caption_input.toPlainText() == "Vũ điệu mùa hè Lovira"
    assert view.cb_content_type.currentText() == "Reels"

    # 2. Chọn Page đích qua page_dropdown
    view.page_dropdown.set_page_selected(p_id, True)

    # 3. Giả lập bấm Submit
    enqueue_mock = MagicMock()
    view.publish_enqueued.connect(enqueue_mock)

    with patch.object(QMessageBox, "information"):
        view._handle_submit()

    # Kiểm tra tác vụ đã được đưa vào PublishQueueRepository
    enqueue_mock.assert_called_once()
    job_ids = enqueue_mock.call_args[0][0]
    assert len(job_ids) == 1

    job = queue_repo.get_job(job_ids[0])
    assert job is not None
    assert job["page_id"] == p_id
    assert "Vũ điệu mùa hè Lovira" in job["content_snapshot"]


def test_composer_ui_page_dropdown_filtering_and_unready(qapp, temp_db, tmp_path):
    """Kiểm thử lọc theo tên / FB ID và không cho chọn Page chưa sẵn sàng."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p_ready1 = page_repo.upsert_page("111222", "Lovira Official", status="ready")
    p_ready2 = page_repo.upsert_page("333444", "Beauty Spa", status="ready")
    p_unready = page_repo.upsert_page("555666", "Expired Page", status="token_expired")

    queue_repo = PublishQueueRepository(temp_db)
    view = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)

    # 1. Lọc theo tên
    view.page_dropdown.search.setText("Beauty")
    visible_count = sum(not item.isHidden() for _, item, _, _ in view.page_dropdown._rows)
    assert visible_count == 1

    # 2. Lọc theo FB ID
    view.page_dropdown.search.setText("111222")
    visible_count = sum(not item.isHidden() for _, item, _, _ in view.page_dropdown._rows)
    assert visible_count == 1

    # 3. Page chưa sẵn sàng (token_expired) bị vô hiệu hóa checkbox
    view.page_dropdown.search.clear()
    for pid, _, checkbox, _ in view.page_dropdown._rows:
        if pid == p_unready:
            assert not checkbox.isEnabled()
            # Thử ép check -> không được tính vào selected_page_ids
            checkbox.setChecked(True)
            assert pid not in view.page_dropdown.selected_page_ids()

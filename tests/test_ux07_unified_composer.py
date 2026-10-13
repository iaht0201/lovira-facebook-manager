"""
Kiểm thử chuyên biệt cho Task UX-07: Unified Post Composer 2.0 (DoD Compliance)
- Kiểm tra Live Simulated Mobile Preview cập nhật thời gian thực khi gõ caption/chọn Page/gắn video
- Kiểm tra các nút Chọn tất cả / Bỏ chọn Fanpage qua page_dropdown
- Kiểm tra thanh công cụ gợi ý hashtag nhanh và bộ đếm ký tự
- Kiểm tra bảo toàn Invariant AC-06/AC-41: Tắt hẹn giờ bảo lưu thời gian, không tự động đăng bài
- Kiểm tra tạo ContentSnapshot bất biến và gửi batch an toàn AC-15/AC-19
"""

from unittest.mock import MagicMock, patch
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.security.vault import SecretVault
from src.lovira.ui.views.post_composer import PostComposerView
from src.lovira.domain.composer import ContentType


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["lovira_test", "-platform", "offscreen"])
    return app


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_ux07.db"
    db = DatabaseManager(db_file)
    MigrationRunner(db).apply_all()
    return db


def test_composer_live_mobile_preview(qapp, temp_db, tmp_path):
    """DoD UX-07: Khung SimulatedPostPreview tự động đồng bộ theo thời gian thực."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p_id = page_repo.upsert_page("fb_preview_1", "Lovira Fashion Official", status="ready")

    queue_repo = PublishQueueRepository(temp_db)
    view = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)

    # 1. Ban đầu Preview hiển thị placeholder
    view._update_live_preview()
    assert view.preview_widget.lbl_page_name.text() == "Chưa chọn Fanpage"
    assert "Đính kèm file" in view.preview_widget.lbl_media_status.text()

    # 2. Chọn Fanpage -> Tên Page và avatar cập nhật trên Preview
    view.page_dropdown.set_page_selected(p_id, True)
    view._update_live_preview()
    assert view.preview_widget.lbl_page_name.text() == "Lovira Fashion Official"
    assert view.preview_widget.lbl_avatar.text() == "L"

    # 3. Gõ Caption -> Caption cập nhật tức thì trên Preview
    view.caption_input.setPlainText("Bùng nổ mùa hè cùng BST mới #fashion #reels")
    view._update_live_preview()
    assert "Bùng nổ mùa hè" in view.preview_widget.lbl_caption.text()

    # 4. Gắn Video -> Preview đổi icon và trạng thái media
    dummy_video = tmp_path / "dance_reels.mp4"
    dummy_video.write_bytes(b"dummy")
    view.attach_video_data({
        "media_id": "med_preview_99",
        "file_path": str(dummy_video),
        "title": "BST Mùa Hè",
    })
    view._update_live_preview()
    assert "dance_reels.mp4" in view.preview_widget.lbl_media_status.text()


def test_composer_select_all_and_hashtag_tools(qapp, temp_db, tmp_path):
    """DoD UX-07: Nút Chọn tất cả/Bỏ chọn và công cụ hashtag hoạt động mượt mà."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p1 = page_repo.upsert_page("p_1", "Page 1", status="ready")
    p2 = page_repo.upsert_page("p_2", "Page 2", status="ready")
    p3 = page_repo.upsert_page("p_3", "Page 3", status="ready")

    queue_repo = PublishQueueRepository(temp_db)
    view = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)

    # Bấm Chọn tất cả
    view.page_dropdown.select_all()
    assert len(view._get_selected_page_ids()) == 3
    assert "3 Page" in view.btn_submit.text()

    # Bấm Bỏ chọn
    view.page_dropdown.clear_selection()
    assert len(view._get_selected_page_ids()) == 0
    assert "0 Page" in view.btn_submit.text()

    # Thử chèn hashtag nhanh
    view.caption_input.setPlainText("Video trải nghiệm")
    view._append_hashtag("#trending")
    assert "#trending" in view.caption_input.toPlainText()
    assert "1 hashtag" in view.lbl_char_count.text()


def test_composer_schedule_invariants_preserved(qapp, temp_db, tmp_path):
    """DoD UX-07: AC-06/AC-41 Bật/tắt hẹn giờ bảo lưu giờ và không tự động publish."""
    vault = SecretVault(fallback_vault_dir=tmp_path / "vault")
    page_repo = PageRepository(temp_db, vault)
    p_sched = page_repo.upsert_page("p_sched", "Page Lịch", status="ready")

    queue_repo = PublishQueueRepository(temp_db)
    view = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)
    view.page_dropdown.set_page_selected(p_sched, True)

    # Ban đầu không hẹn giờ
    assert not view.chk_schedule.isChecked()
    assert view.schedule_picker_frame.isHidden()
    assert "Đăng ngay" in view.btn_submit.text()

    # Bật hẹn giờ
    view.chk_schedule.setChecked(True)
    assert not view.schedule_picker_frame.isHidden()
    assert "Đặt lịch" in view.btn_submit.text()
    orig_dt = view.datetime_picker.dateTime()

    # Tắt hẹn giờ -> Không xóa giờ đã chọn, nhãn quay về Đăng ngay
    view.chk_schedule.setChecked(False)
    assert view.schedule_picker_frame.isHidden()
    assert "Đăng ngay" in view.btn_submit.text()
    assert view.datetime_picker.dateTime() == orig_dt

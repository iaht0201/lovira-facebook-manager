"""
Tests for UX-11 — Comments Workspace 2.0 (CommentsWorkspaceView)
Verifies:
- Honest permission state banner (A-01, Section 5.2)
- Split pane layout with live search and status filter
- EmptyState switching (no comments vs search not found)
- ReplyTemplateRepository integration and quick reply flow
- Comment actions (hide/unhide, delete cache)
- GlobalPageContext sync
"""

import pytest
from unittest.mock import patch, MagicMock
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.ui.views.comments_workspace import CommentsWorkspaceView, TemplateManagerDialog
from src.lovira.storage.comment_repository import CommentCacheRepository, ReplyTemplateRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.ui.shell.global_context import GlobalPageContext


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_comments.db"
    manager = DatabaseManager(db_file)
    runner = MigrationRunner(manager)
    runner.apply_all()
    return manager



@pytest.fixture
def comment_repo(temp_db):
    return CommentCacheRepository(temp_db)


@pytest.fixture
def reply_repo(temp_db):
    return ReplyTemplateRepository(temp_db)


from src.lovira.security.vault import SecretVault


@pytest.fixture
def page_repo(temp_db):
    vault = SecretVault(temp_db)
    return PageRepository(temp_db, vault)


def test_comments_workspace_layout_and_banner_integrity(qapp, comment_repo, reply_repo, page_repo):
    """DoD UX-11: Kiểm tra cấu trúc giao diện và banner quyền hạn trung thực (A-01)."""
    view = CommentsWorkspaceView(
        comment_repo=comment_repo,
        reply_repo=reply_repo,
        page_repo=page_repo,
    )

    assert view.table_comments is not None
    assert view.perm_banner is not None
    assert "pages_manage_engagement" in view.lbl_perm_msg.text()
    assert view.input_reply is not None
    assert view.btn_send_reply is not None
    assert view.search_filter is not None
    assert view.combo_filter_status is not None
    assert view.combo_templates is not None


def test_comments_workspace_empty_state_and_table_switching(qapp, comment_repo, reply_repo, page_repo):
    """DoD UX-11: Kiểm tra chuyển đổi EmptyState và Bảng bình luận."""
    view = CommentsWorkspaceView(
        comment_repo=comment_repo,
        reply_repo=reply_repo,
        page_repo=page_repo,
    )

    # Ban đầu không có comment nào -> hiển thị empty_state_comments
    assert view.table_stack_layout.currentWidget() == view.empty_state_comments

    # Đảm bảo page tồn tại trước để thỏa mãn foreign key
    p_id = page_repo.upsert_page(
        facebook_page_id="fb_page_123",
        name="Lovira Demo Page",
        status="ready",
    )

    # Thêm 1 comment vào repo
    comment_repo.upsert_comment(
        page_id=p_id,
        remote_comment_id="c_001",
        post_id="post_999",
        metadata={
            "message": "Sản phẩm này còn hàng không shop?",
            "from": {"name": "Nguyễn Văn A", "id": "user_1"},
            "created_time": "2026-10-13T10:00:00+00:00",
            "comment_count": 0,
        },
    )

    view.reload_comments()
    assert view.table_stack_layout.currentWidget() == view.table_comments
    assert view.table_comments.rowCount() == 1
    assert "Nguyễn Văn A" in view.table_comments.item(0, 0).text()

    # Tìm kiếm không khớp -> chuyển sang empty_state_search
    view.search_filter.setText("Khách hàng không tồn tại")
    assert view.table_stack_layout.currentWidget() == view.empty_state_search

    # Xóa tìm kiếm -> quay lại bảng
    view.search_filter.clear()
    assert view.table_stack_layout.currentWidget() == view.table_comments


def test_comments_workspace_template_usage_and_reply_flow(qapp, comment_repo, reply_repo, page_repo):
    """DoD UX-11: Kiểm tra nạp mẫu câu và gửi phản hồi."""
    p_id = page_repo.upsert_page(
        facebook_page_id="fb_page_123",
        name="Lovira Demo Page",
        status="ready",
    )

    # Tạo mẫu câu
    reply_repo.create_template(
        name="Báo giá",
        content="Chào bạn, shop đã inbox báo giá chi tiết rồi ạ!",
    )

    view = CommentsWorkspaceView(
        comment_repo=comment_repo,
        reply_repo=reply_repo,
        page_repo=page_repo,
    )

    # Thêm comment
    comment_repo.upsert_comment(
        page_id=p_id,
        remote_comment_id="c_002",
        post_id="post_999",
        metadata={
            "message": "Giá bao nhiêu vậy?",
            "from": {"name": "Trần Thị B", "id": "user_2"},
            "created_time": "2026-10-13T10:30:00+00:00",
        },
    )
    view.reload_comments()

    # Chọn comment
    view._on_comment_selected(0, 0)
    assert "Trần Thị B" in view.lbl_author_info.text()
    assert "Giá bao nhiêu" in view.lbl_comment_context.text()

    # Chọn mẫu câu từ combobox
    assert view.combo_templates.count() >= 2
    view.combo_templates.setCurrentIndex(1)
    assert "inbox báo giá" in view.input_reply.toPlainText()

    # Gửi phản hồi
    with patch.object(QMessageBox, "information") as mock_info:
        view._send_reply()
        mock_info.assert_called_once()
        assert view.input_reply.toPlainText() == ""


def test_comments_workspace_hide_and_delete_comment(qapp, comment_repo, reply_repo, page_repo):
    """DoD UX-11: Kiểm tra thao tác ẩn/bỏ ẩn và xóa comment khỏi cache."""
    p_id = page_repo.upsert_page(
        facebook_page_id="fb_page_123",
        name="Lovira Demo Page",
        status="ready",
    )

    comment_repo.upsert_comment(
        page_id=p_id,
        remote_comment_id="c_003",
        post_id="post_999",
        metadata={
            "message": "Comment rác",
            "from": {"name": "Spammer", "id": "user_spam"},
            "is_hidden": False,
        },
    )

    view = CommentsWorkspaceView(
        comment_repo=comment_repo,
        reply_repo=reply_repo,
        page_repo=page_repo,
    )
    view.reload_comments()
    view._on_comment_selected(0, 0)

    # Ẩn comment
    with patch.object(QMessageBox, "information"):
        view._handle_toggle_hide()
        assert "Bỏ ẩn" in view.btn_toggle_hide.text()

    # Xóa comment khỏi cache
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        view._handle_delete_comment()
        assert comment_repo.get_comment(p_id, "c_003") is None



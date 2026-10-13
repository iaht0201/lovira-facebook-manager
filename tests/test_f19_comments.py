"""
Unit test cho F-19: Quản lý Bình luận & Reply Templates (BR-04, AC-10)
"""

import pytest
from unittest.mock import MagicMock, patch
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.comment_repository import (
    CommentCacheRepository,
    ReplyTemplateRepository,
    FacebookCommentService,
)
from src.lovira.integrations.facebook.client import FacebookGraphClient


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_comments.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_comment_cache_crud(temp_db):
    """Kiểm tra lưu trữ, tìm kiếm và xóa bình luận trong SQLite cache."""
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('page_c1', 'fb_c1', 'Page 1');")

    repo = CommentCacheRepository(temp_db)

    # 1. Upsert bình luận
    repo.upsert_comment(
        page_id="page_c1",
        remote_comment_id="cmt_001",
        post_id="post_99",
        metadata={"message": "Sản phẩm này còn size M không shop?", "from": {"name": "Nguyễn Văn A"}},
    )
    repo.upsert_comment(
        page_id="page_c1",
        remote_comment_id="cmt_002",
        post_id="post_99",
        metadata={"message": "Cho mình xin giá với", "from": {"name": "Trần Thị B"}},
    )

    # 2. Get comment
    c1 = repo.get_comment("page_c1", "cmt_001")
    assert c1 is not None
    assert c1["post_id"] == "post_99"
    assert "size M" in c1["metadata"]["message"]

    # 3. List comments
    cmts = repo.list_comments(page_id="page_c1", post_id="post_99")
    assert len(cmts) == 2

    # Tìm kiếm theo từ khóa
    search_res = repo.list_comments(search_query="size M")
    assert len(search_res) == 1
    assert search_res[0]["remote_comment_id"] == "cmt_001"

    # 4. Xóa bình luận
    assert repo.delete_comment("page_c1", "cmt_001") is True
    assert repo.get_comment("page_c1", "cmt_001") is None


def test_reply_template_crud_and_page_scoping(temp_db):
    """Kiểm tra mẫu trả lời và phạm vi áp dụng Page (Section 6.3)."""
    repo = ReplyTemplateRepository(temp_db)

    # 1. Tạo mẫu áp dụng cho TẤT CẢ các Page (page_scope is None)
    t1_id = repo.create_template(
        name="Chào mừng chung",
        content="Dạ Lovira xin chào quý khách ạ!",
    )

    # 2. Tạo mẫu chỉ áp dụng riêng cho Page A
    t2_id = repo.create_template(
        name="Tư vấn Size Đầm Dạ Hội",
        content="Dạ mẫu này bên em còn đủ size từ S đến XL ạ.",
        page_scope=["page_fashion_1"],
    )

    # 3. Lọc mẫu theo page_id
    # Page A sẽ thấy cả mẫu chung và mẫu riêng
    templates_for_page_a = repo.list_templates(page_id="page_fashion_1")
    assert len(templates_for_page_a) == 2

    # Page B sẽ CHỈ thấy mẫu chung
    templates_for_page_b = repo.list_templates(page_id="page_food_2")
    assert len(templates_for_page_b) == 1
    assert templates_for_page_b[0]["id"] == t1_id

    # 4. Cập nhật mẫu
    assert repo.update_template(t1_id, content="Dạ Lovira hân hạnh phục vụ quý khách ạ!") is True
    updated_t1 = [t for t in repo.list_templates() if t["id"] == t1_id][0]
    assert "hân hạnh phục vụ" in updated_t1["content"]

    # 5. Xóa mẫu
    assert repo.delete_template(t2_id) is True
    assert len(repo.list_templates(page_id="page_fashion_1")) == 1


def test_facebook_comment_sync_and_reply(temp_db):
    """Kiểm tra tích hợp Facebook Graph API cho bình luận."""
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('page_test', 'fb_page_test', 'Test Page');")

    repo = CommentCacheRepository(temp_db)
    fb_client = FacebookGraphClient()

    # 1. Mock Sync comments
    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.json.return_value = {
        "data": [
            {
                "id": "cmt_fb_123",
                "message": "Shop ở đâu vậy?",
                "created_time": "2026-10-13T10:00:00+0000",
            }
        ]
    }

    # 2. Mock Reply comment
    mock_post_resp = MagicMock()
    mock_post_resp.status_code = 200
    mock_post_resp.json.return_value = {"id": "reply_fb_456"}

    # 3. Mock Hide comment
    mock_hide_resp = MagicMock()
    mock_hide_resp.status_code = 200
    mock_hide_resp.json.return_value = {"success": True}

    with patch.object(fb_client.session, "get", return_value=mock_get_resp), \
         patch.object(fb_client.session, "post", side_effect=[mock_post_resp, mock_hide_resp]):

        service = FacebookCommentService(fb_client, repo)

        # Sync
        synced = service.sync_comments_for_post("page_test", "post_001", "mock_tok")
        assert len(synced) == 1
        assert synced[0]["id"] == "cmt_fb_123"

        # Reply
        reply_id = service.reply_to_comment("cmt_fb_123", "Dạ shop ở Hà Nội ạ!", "mock_tok")
        assert reply_id == "reply_fb_456"

        # Hide
        hide_ok = service.hide_comment("cmt_fb_123", is_hidden=True, page_token="mock_tok")
        assert hide_ok is True

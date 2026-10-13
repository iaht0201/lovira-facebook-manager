"""
Unit test cho F-18: Đồng bộ Bài viết & Giám sát Facebook Reels (BR-03, AC-10)
"""

import pytest
from unittest.mock import MagicMock, patch
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.post_repository import PostCacheRepository, FacebookPostSyncService
from src.lovira.integrations.facebook.client import FacebookGraphClient


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_posts.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


def test_post_cache_crud_and_search(temp_db):
    """Kiểm tra lưu trữ, tìm kiếm và xóa bài viết trong SQLite cache."""
    # Tạo Page mẫu
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('page_p1', 'fb_p1', 'Page 1');")
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('page_p2', 'fb_p2', 'Page 2');")

    repo = PostCacheRepository(temp_db)

    # 1. Upsert posts
    repo.upsert_post(
        page_id="page_p1",
        remote_post_id="post_101",
        post_type="text",
        metadata={"caption": "Khuyến mãi mùa hè 50%"},
    )
    repo.upsert_post(
        page_id="page_p1",
        remote_post_id="post_102",
        post_type="reels",
        metadata={"caption": "Review đầm dạ hội cao cấp", "views": None},
    )
    repo.upsert_post(
        page_id="page_p2",
        remote_post_id="post_201",
        post_type="reels",
        metadata={"caption": "Video nấu ăn ngon", "views": 1500},
    )

    # 2. Get post
    p1 = repo.get_post("page_p1", "post_101")
    assert p1 is not None
    assert p1["post_type"] == "text"
    assert p1["metadata"]["caption"] == "Khuyến mãi mùa hè 50%"

    # 3. List posts with filters
    p1_reels = repo.list_posts(page_id="page_p1", post_type="reels")
    assert len(p1_reels) == 1
    assert p1_reels[0]["remote_post_id"] == "post_102"

    # Search by keyword
    search_res = repo.list_posts(search_query="dạ hội")
    assert len(search_res) == 1
    assert search_res[0]["remote_post_id"] == "post_102"

    # 4. Delete post
    assert repo.delete_post("page_p1", "post_101") is True
    assert repo.get_post("page_p1", "post_101") is None


def test_reels_metadata_missing_insights_ac10():
    """
    AC-10: Đồng bộ chỉ số không có quyền đọc (views, insights)
    -> Hiện thiếu dữ liệu (None), tuyệt đối không tự gán số 0.
    """
    raw_reel_no_insights = {
        "id": "reel_888999",
        "description": "Reel thử nghiệm thiếu quyền",
        "created_time": "2026-10-13T08:00:00+0000",
        "permalink_url": "https://facebook.com/reel/888999",
        "picture": "https://fbcdn.net/thumb.jpg",
    }

    parsed = FacebookPostSyncService.parse_reels_metadata(raw_reel_no_insights)
    assert parsed["id"] == "reel_888999"
    assert parsed["caption"] == "Reel thử nghiệm thiếu quyền"
    assert parsed["views"] is None  # AC-10: None (Chưa có dữ liệu), không phải 0!
    assert parsed["likes"] is None  # AC-10: None, không phải 0!


def test_sync_reels_for_page(temp_db):
    """Kiểm tra đồng bộ Reels qua API và lưu vào cache."""
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('page_sync_1', 'fb_sync_1', 'Page Sync');")

    repo = PostCacheRepository(temp_db)
    fb_client = FacebookGraphClient()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "id": "reel_synced_1",
                "description": "Reel đã đồng bộ thành công",
                "created_time": "2026-10-13T09:00:00+0000",
                "permalink_url": "https://facebook.com/reel/synced1",
                "picture": "https://fbcdn.net/pic1.jpg",
            }
        ]
    }

    with patch.object(fb_client.session, "get", return_value=mock_resp):
        service = FacebookPostSyncService(fb_client, repo)
        synced = service.sync_reels_for_page(
            page_id="page_sync_1",
            facebook_page_id="fb_sync_1",
            page_token="mock_token",
        )

    assert len(synced) == 1
    assert synced[0]["id"] == "reel_synced_1"
    assert synced[0]["views"] is None  # AC-10

    cached_post = repo.get_post("page_sync_1", "reel_synced_1")
    assert cached_post is not None
    assert cached_post["post_type"] == "reels"
    assert cached_post["metadata"]["caption"] == "Reel đã đồng bộ thành công"

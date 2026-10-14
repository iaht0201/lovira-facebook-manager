"""
Unit tests for Comment Templates, Shopee Link Preview, and First Comment Synchronization.
Covers:
1. LinkPreviewService: Shopee URL detection, URL extraction, OpenGraph & price parsing.
2. ReplyTemplateRepository: Schema migration, singleton access, CRUD, batch import.
3. FacebookPublisher First Comment synchronization: Auto-posting comment after post/video/reels.
4. MediaEditPostDialog & PostComposerView: Quick template selection and first_comment snapshot persistence.
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.services.link_preview import LinkPreviewService
from src.lovira.storage.comment_repository import ReplyTemplateRepository
from src.lovira.integrations.facebook.publisher import GraphPublishAdapter, PublishResult
from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
from src.lovira.ui.views.video_workspace import MediaEditPostDialog
from src.lovira.ui.views.post_composer import PostComposerView
from src.lovira.storage.page_repository import PageRepository
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.security.vault import SecretVault


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_comments_sync.db"
    manager = DatabaseManager(db_file)
    runner = MigrationRunner(manager)
    runner.apply_all()
    return manager


@pytest.fixture
def reply_repo(temp_db):
    return ReplyTemplateRepository.get_instance(temp_db)


@pytest.fixture
def page_repo(temp_db):
    vault = SecretVault(temp_db)
    return PageRepository(temp_db, vault)


@pytest.fixture
def queue_repo(temp_db):
    return PublishQueueRepository(temp_db)


# -------------------------------------------------------------------------
# 1. LinkPreviewService Tests
# -------------------------------------------------------------------------

def test_shopee_url_detection():
    service = LinkPreviewService.get_instance()
    assert service.is_shopee_url("https://shopee.vn/product/123/456") is True
    assert service.is_shopee_url("https://s.shopee.vn/aBcDe123") is True
    assert service.is_shopee_url("https://shope.ee/xyz789") is True
    assert service.is_shopee_url("https://lazada.vn/item") is False
    assert service.is_shopee_url("https://google.com") is False


def test_url_extraction():
    service = LinkPreviewService.get_instance()
    text = "Áo đẹp ghé mua tại https://s.shopee.vn/abc123 nhé các bạn! Hoặc link phụ: https://shope.ee/xyz456"
    urls = service.extract_urls(text)
    assert len(urls) == 2
    assert "https://s.shopee.vn/abc123" in urls
    assert "https://shope.ee/xyz456" in urls


def test_link_preview_fetch_shopee_html(tmp_path):
    service = LinkPreviewService.get_instance()
    mock_url = "https://shopee.vn/product-sample"
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta property="og:title" content="Áo Thun Nữ Cotton Cao Cấp | Shopee Việt Nam">
        <meta property="og:description" content="Mua Áo Thun Nữ Cotton Cao Cấp giá tốt. Mua hàng qua mạng uy tín, tiện lợi. Shopee đảm bảo nhận hàng, hoặc được hoàn lại tiền Giao Hàng Miễn Phí.">
        <meta property="og:image" content="https://cf.shopee.vn/file/sample_image.jpg">
        <meta property="product:price:amount" content="149000">
        <meta property="product:price:currency" content="VND">
    </head>
    <body></body>
    </html>
    """

    def mock_get(url, *args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.url = url
        if "sample_image.jpg" in url:
            resp.content = b"fake-image-bytes"
        else:
            resp.text = html_content
        return resp

    with patch("requests.get", side_effect=mock_get):
        preview = service.fetch_preview(mock_url)
        assert preview is not None
        assert "Áo Thun Nữ Cotton Cao Cấp" in preview["title"]
        assert "Shopee Việt Nam" not in preview["title"]  # Cleaned title
        assert "149.000đ" in preview["price"]
        assert preview["image_url"] == "https://cf.shopee.vn/file/sample_image.jpg"
        assert preview["local_image_path"] is not None
        assert Path(preview["local_image_path"]).exists()


# -------------------------------------------------------------------------
# 2. ReplyTemplateRepository Tests
# -------------------------------------------------------------------------

def test_reply_template_schema_and_singleton(temp_db):
    repo1 = ReplyTemplateRepository.get_instance(temp_db)
    repo2 = ReplyTemplateRepository.get_instance()
    assert repo1 is repo2

    # Check that extended columns exist
    with temp_db.transaction() as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(reply_templates);").fetchall()]
        assert "product_url" in cols
        assert "image_url" in cols
        assert "local_image_path" in cols
        assert "price" in cols


def test_reply_template_crud_with_product_info(reply_repo):
    tpl_id = reply_repo.create_template(
        name="Đầm Hoa Nhí Vintage",
        content="Link đầm hoa nhí mình mặc trong video ở đây nhé các nàng: https://s.shopee.vn/dam-hoa",
        product_url="https://s.shopee.vn/dam-hoa",
        price="189.000đ",
    )
    assert tpl_id is not None

    templates = reply_repo.list_templates()
    matching = [t for t in templates if t["id"] == tpl_id]
    assert len(matching) == 1
    t = matching[0]
    assert t["name"] == "Đầm Hoa Nhí Vintage"
    assert t["price"] == "189.000đ"
    assert t["product_url"] == "https://s.shopee.vn/dam-hoa"


def test_reply_template_batch_import(reply_repo):
    items = [
        {
            "name": "Son Kem Lì Black Rouge",
            "content": "Mua son Black Rouge chính hãng tại: https://shopee.vn/son-br",
            "product_url": "https://shopee.vn/son-br",
            "price": "135.000đ",
        },
        {
            "name": "Kẹp Tóc Càng Cua Hàn Quốc",
            "content": "Set 5 kẹp tóc phong cách Hàn: https://shopee.vn/kep-toc",
            "product_url": "https://shopee.vn/kep-toc",
            "price": "29.000đ",
        },
    ]

    count = reply_repo.import_templates(items)
    assert count == 2

    templates = reply_repo.list_templates()
    names = [t["name"] for t in templates]
    assert "Son Kem Lì Black Rouge" in names
    assert "Kẹp Tóc Càng Cua Hàn Quốc" in names


# -------------------------------------------------------------------------
# 3. Facebook Comment Publishing Synchronization Tests
# -------------------------------------------------------------------------

def test_facebook_publisher_first_comment_sync():
    publisher = GraphPublishAdapter(timeout=5)

    snapshot = ContentSnapshot(
        batch_id="b1",
        page_id="p1",
        content_type=ContentType.REELS,
        final_caption="Test Reels Caption",
        media_path="fake/path.mp4",
        first_comment="Link sản phẩm trong video: https://shopee.vn/sample",
    )

    with patch.object(
        publisher,
        "publish_reels",
        return_value=PublishResult(success=True, post_id="reels_12345", video_id="vid_12345")
    ):
        with patch.object(
            publisher,
            "publish_comment",
            return_value=PublishResult(success=True, post_id="comment_99999")
        ) as mock_comment:
            with patch("time.sleep"):  # Avoid real delay in test
                res = publisher.publish("token_xyz", snapshot, facebook_page_id="page_111")

                assert res.success is True
                assert res.comment_id == "comment_99999"
                mock_comment.assert_called_once_with(
                    "token_xyz",
                    "reels_12345",
                    "Link sản phẩm trong video: https://shopee.vn/sample",
                )


def test_facebook_publisher_first_comment_fallback():
    publisher = GraphPublishAdapter(timeout=5)

    snapshot = ContentSnapshot(
        batch_id="b2",
        page_id="p2",
        content_type=ContentType.VIDEO,
        final_caption="Video caption",
        media_path="fake/video.mp4",
        first_comment="Bình luận đầu tiên",
    )

    with patch.object(
        publisher,
        "publish_video",
        return_value=PublishResult(success=True, post_id=None, video_id="vid_777")
    ):
        # 1st call fails, 2nd call with composite ID succeeds
        call_count = 0
        def fake_publish_comment(token, target_id, message):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return PublishResult(success=False, error_message="Object does not exist")
            return PublishResult(success=True, post_id="comment_composite_888")

        with patch.object(publisher, "publish_comment", side_effect=fake_publish_comment):
            with patch("time.sleep"):
                res = publisher.publish("token_abc", snapshot, facebook_page_id="100200300")

                assert res.success is True
                assert res.comment_id == "comment_composite_888"
                assert call_count == 2


# -------------------------------------------------------------------------
# 4. UI: MediaEditPostDialog & PostComposerView Comment Quick Picker
# -------------------------------------------------------------------------

def test_media_edit_post_dialog_template_apply(qapp, temp_db, reply_repo):
    tpl = {
        "id": "tpl_1",
        "name": "Tai Nghe Bluetooth TWS",
        "content": "Tai nghe chống ồn cực tốt, link mua chính hãng: https://s.shopee.vn/tws",
        "product_url": "https://s.shopee.vn/tws",
        "price": "350.000đ",
        "local_image_path": "",
    }

    asset = {
        "id": "asset_1",
        "title": "Unbox tai nghe",
        "caption": "Trải nghiệm tai nghe mới",
        "tags": "#tws",
        "first_comment": "",
        "local_path": "C:/dummy.mp4",
        "duration": 60,
        "size_bytes": 1024000,
    }

    dialog = MediaEditPostDialog(asset=asset, pages=[{"id": "p1", "name": "Fanpage 1"}])
    assert dialog.txt_comment.toPlainText() == ""
    assert dialog.product_preview_frame.isHidden()

    # Apply template
    dialog._apply_template(tpl)
    assert "Tai nghe chống ồn cực tốt" in dialog.txt_comment.toPlainText()
    assert not dialog.product_preview_frame.isHidden()
    assert "Tai Nghe Bluetooth TWS" in dialog.lbl_cmt_pv_title.text()
    assert "350.000đ" in dialog.lbl_cmt_pv_sub.text()

    # Remove preview
    dialog._on_remove_product_preview()
    assert dialog.product_preview_frame.isHidden()


def test_post_composer_first_comment_snapshot(qapp, temp_db, reply_repo, page_repo, queue_repo):
    composer = PostComposerView(page_repo=page_repo, queue_repo=queue_repo)

    # Insert a dummy page
    with temp_db.transaction() as conn:
        conn.execute("INSERT INTO pages (id, facebook_page_id, name, status) VALUES ('page_test_1', 'fb_p1', 'Test Page 1', 'ready');")
    composer.reload_pages()

    # Apply a template to composer
    tpl = {
        "id": "tpl_2",
        "name": "Váy Suông Công Sở",
        "content": "Váy suông mát mẻ hè 2026: https://s.shopee.vn/vay-suong",
        "product_url": "https://s.shopee.vn/vay-suong",
        "price": "220.000đ",
    }
    composer._apply_comment_template(tpl)

    assert "Váy suông mát mẻ hè 2026" in composer.comment_input.toPlainText()
    assert not composer.product_preview_frame.isHidden()
    assert "Váy Suông Công Sở" in composer.lbl_cmt_pv_title.text()
    assert "220.000đ" in composer.lbl_cmt_pv_sub.text()

    # Enqueue a post snapshot with first comment
    composer.cb_content_type.setCurrentText("Văn bản")
    composer._select_all_pages()
    composer.caption_input.setPlainText("Hôm nay diện mẫu váy mới đi làm!")
    composer._handle_submit()

    # Verify jobs in queue_repo
    jobs = queue_repo.list_jobs(limit=5)
    assert len(jobs) >= 1
    job = jobs[0]
    snapshot = ContentSnapshot.from_json(job["content_snapshot"])
    assert snapshot.first_comment == "Váy suông mát mẻ hè 2026: https://s.shopee.vn/vay-suong"

    # Verify composer fields got reset
    assert composer.comment_input.toPlainText() == ""
    assert composer.product_preview_frame.isHidden()

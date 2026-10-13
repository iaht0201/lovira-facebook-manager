import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
from src.lovira.integrations.facebook.publisher import GraphPublishAdapter, PublishResult


def test_enqueue_batch_double_click_protection():
    # AC-15: Bấm đăng hai lần rất nhanh -> Chỉ một nhóm tác vụ cho cùng request
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(db_path)
        MigrationRunner(db).apply_all()
        queue = PublishQueueRepository(db)

        # Tạo Page mẫu
        with db.transaction() as conn:
            conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p-1', '101', 'Page 1');")
            conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES ('p-2', '102', 'Page 2');")

        snap1 = ContentSnapshot(
            batch_id="b-1",
            page_id="p-1",
            content_type=ContentType.TEXT,
            final_caption="Caption 1",
            schedule_mode=ScheduleMode.LOCAL,
        )
        snap2 = ContentSnapshot(
            batch_id="b-1",
            page_id="p-2",
            content_type=ContentType.TEXT,
            final_caption="Caption 2",
            schedule_mode=ScheduleMode.LOCAL,
        )

        client_req_id = "req_click_once_999"

        # Lần bấm thứ 1
        job_ids_first = queue.enqueue_batch(client_req_id, [snap1, snap2])
        assert len(job_ids_first) == 2

        # Lần bấm thứ 2 rất nhanh với cùng client_request_id (AC-15)
        job_ids_second = queue.enqueue_batch(client_req_id, [snap1, snap2])
        assert job_ids_first == job_ids_second

        # Kiểm tra database chỉ có đúng 2 job, không bị nhân đôi lên 4
        jobs = queue.list_jobs_by_batch("b-1")
        assert len(jobs) == 2


def test_multi_page_independent_results():
    # AC-05: Đăng một nội dung lên ba Page, một Page lỗi -> Hai kết quả thành công được giữ; retry chỉ Page lỗi
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(db_path)
        MigrationRunner(db).apply_all()
        queue = PublishQueueRepository(db)

        with db.transaction() as conn:
            for pid in ["p-1", "p-2", "p-3"]:
                conn.execute("INSERT INTO pages (id, facebook_page_id, name) VALUES (?, ?, ?);", (pid, pid, f"Page {pid}"))

        snapshots = [
            ContentSnapshot("b-10", "p-1", ContentType.TEXT, "Hello P1"),
            ContentSnapshot("b-10", "p-2", ContentType.TEXT, "Hello P2"),
            ContentSnapshot("b-10", "p-3", ContentType.TEXT, "Hello P3"),
        ]
        job_ids = queue.enqueue_batch("req_multi_3", snapshots)
        assert len(job_ids) == 3

        # Giả lập Page 1 & 2 thành công, Page 3 lỗi token
        queue.update_job_outcome(job_ids[0], state="published", post_id="fb_post_111")
        queue.update_job_outcome(job_ids[1], state="published", post_id="fb_post_222")
        queue.update_job_outcome(job_ids[2], state="failed_retryable", last_error_code="TOKEN_EXPIRED")

        j1 = queue.get_job(job_ids[0])
        j2 = queue.get_job(job_ids[1])
        j3 = queue.get_job(job_ids[2])

        assert j1["state"] == "published"
        assert j1["remote_scheduled_id"] == "fb_post_111"

        assert j2["state"] == "published"
        assert j2["remote_scheduled_id"] == "fb_post_222"

        assert j3["state"] == "failed_retryable"
        assert j3["last_error_code"] == "TOKEN_EXPIRED"


def test_graph_publish_reels_flow():
    # Section 6.2 & S8: Kiểm tra quy trình 3 bước đăng Facebook Reels
    adapter = GraphPublishAdapter()

    with tempfile.TemporaryDirectory() as tmpdir:
        dummy_video = Path(tmpdir) / "reels_test.mp4"
        dummy_video.write_bytes(b"REELS_VIDEO_BINARY_DATA_1234567890")

        # Mock Step 1: Start
        step1_resp = MagicMock()
        step1_resp.status_code = 200
        step1_resp.json.return_value = {
            "video_id": "vid_reels_12345",
            "upload_url": "https://rupload.facebook.com/video-upload/v21.0/vid_reels_12345",
        }

        # Mock Step 2: Binary transfer
        step2_resp = MagicMock()
        step2_resp.status_code = 200

        # Mock Step 3: Finish
        step3_resp = MagicMock()
        step3_resp.status_code = 200
        step3_resp.json.return_value = {"success": True}

        def mock_post(url, **kwargs):
            if "video_reels" in url and kwargs.get("data", {}).get("upload_phase") == "start":
                return step1_resp
            if "rupload.facebook.com" in url:
                return step2_resp
            if "video_reels" in url and kwargs.get("data", {}).get("upload_phase") == "finish":
                return step3_resp
            raise ValueError(f"Unexpected url: {url}")

        with patch.object(adapter.session, "post", side_effect=mock_post):
            res = adapter.publish_reels(
                page_token="EAABvalid_page_token",
                page_id="10099",
                description="Test Reels Description",
                video_path=str(dummy_video),
            )

            assert res.success is True
            assert res.video_id == "vid_reels_12345"
            assert res.post_id == "vid_reels_12345"


def test_graph_publish_uses_facebook_page_id():
    """Kiểm tra GraphPublishAdapter.publish dùng facebook_page_id thật thay vì internal page_id."""
    adapter = GraphPublishAdapter()
    snap = ContentSnapshot(
        batch_id="b-99",
        page_id="internal_page_id_xyz",
        content_type=ContentType.TEXT,
        final_caption="Hello Facebook!",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "fb_post_real_777"}

    with patch.object(adapter.session, "post", return_value=mock_resp) as mock_post:
        res = adapter.publish("valid_token", snap, facebook_page_id="1000999888")
        assert res.success is True
        assert res.post_id == "fb_post_real_777"
        called_url = mock_post.call_args[0][0]
        # URL phải chứa ID Facebook thật (1000999888), không chứa internal_page_id_xyz
        assert "1000999888/feed" in called_url
        assert "internal_page_id_xyz" not in called_url


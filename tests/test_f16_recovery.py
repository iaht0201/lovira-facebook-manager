"""
Unit test cho F-16: Khôi phục sự cố, xử lý Unknown & Backoff Retry (RecoveryManager)
Đáp ứng AC-14, AC-21
"""

import pytest
from unittest.mock import MagicMock, patch
from src.lovira.storage.db import DatabaseManager
from src.lovira.storage.migrations import MigrationRunner
from src.lovira.storage.queue_repository import PublishQueueRepository
from src.lovira.storage.page_repository import PageRepository
from src.lovira.security.vault import SecretVault
from src.lovira.integrations.facebook.client import FacebookGraphClient
from src.lovira.domain.composer import ContentSnapshot, ContentType, ScheduleMode
from src.lovira.workers.recovery import RecoveryManager


@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_recovery.db"
    db_manager = DatabaseManager(db_file)
    runner = MigrationRunner(db_manager)
    runner.apply_all()
    return db_manager


@pytest.fixture
def secret_vault(tmp_path):
    return SecretVault(fallback_vault_dir=tmp_path / "vault")


def test_backoff_delay_calculation():
    """AC-21: Thuật toán Exponential Backoff kèm Jitter ngẫu nhiên."""
    delay1 = RecoveryManager.calculate_backoff_delay(attempt_count=1, base_delay_seconds=30.0)
    assert 30.0 <= delay1 <= 40.0

    delay2 = RecoveryManager.calculate_backoff_delay(attempt_count=2, base_delay_seconds=30.0)
    assert 60.0 <= delay2 <= 80.0

    delay_capped = RecoveryManager.calculate_backoff_delay(attempt_count=10, base_delay_seconds=30.0, max_delay_seconds=300.0)
    assert delay_capped <= 400.0


def test_recover_orphaned_jobs(temp_db, secret_vault):
    """AC-14: Tự động chuyển các tác vụ treo sang trạng thái 'unknown' khi khởi động lại."""
    page_repo = PageRepository(temp_db, secret_vault)
    p_id = page_repo.upsert_page(facebook_page_id="p_rec_1", name="Page Recovery")
    page_repo.save_page_token(page_id=p_id, raw_token="tok_1")

    queue_repo = PublishQueueRepository(temp_db)
    client_req_id = "req_rec_01"
    snap = ContentSnapshot(
        batch_id="b_rec_1",
        page_id=p_id,
        content_type=ContentType.TEXT,
        final_caption="Crash test",
        schedule_mode=ScheduleMode.LOCAL,
    )
    job_ids = queue_repo.enqueue_batch(client_req_id, [snap])
    job_id = job_ids[0]

    # Giả lập ứng dụng bị crash khi đang ở trạng thái 'publishing' với lease đã hết hạn
    with temp_db.transaction() as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET state = 'publishing',
                worker_lease_until = '2026-01-01T00:00:00Z'
            WHERE id = ?;
            """,
            (job_id,),
        )

    fb_client = FacebookGraphClient()
    recovery = RecoveryManager(temp_db, queue_repo, page_repo, fb_client)

    recovered_count = recovery.recover_orphaned_jobs()
    assert recovered_count == 1

    updated_job = queue_repo.get_job(job_id)
    assert updated_job["state"] == "unknown"
    assert "Ứng dụng bị dừng đột ngột" in updated_job["blocked_reason"]


def test_reconcile_job_success(temp_db, secret_vault):
    """AC-14: Đối chiếu thành công nếu bài viết đã xuất hiện trên Facebook."""
    page_repo = PageRepository(temp_db, secret_vault)
    p_id = page_repo.upsert_page(facebook_page_id="p_rec_2", name="Page Reconcile")
    page_repo.save_page_token(page_id=p_id, raw_token="tok_rec")

    queue_repo = PublishQueueRepository(temp_db)
    snap = ContentSnapshot(
        batch_id="b_rec_2",
        page_id=p_id,
        content_type=ContentType.TEXT,
        final_caption="Reconcile test",
        schedule_mode=ScheduleMode.LOCAL,
    )
    job_ids = queue_repo.enqueue_batch("req_rec_02", [snap])
    job_id = job_ids[0]

    # Đánh dấu tác vụ là unknown và ghi lại attempt có post_id
    with temp_db.transaction() as conn:
        conn.execute("UPDATE publish_jobs SET state = 'unknown' WHERE id = ?;", (job_id,))
        conn.execute(
            """
            INSERT INTO publish_attempts (id, job_id, attempt_no, post_id, started_at, outcome)
            VALUES ('att_1', ?, 1, 'fb_post_999', '2026-10-13T09:00:00Z', 'unknown');
            """,
            (job_id,),
        )

    fb_client = FacebookGraphClient()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"id": "fb_post_999"}

    with patch.object(fb_client.session, "get", return_value=mock_resp):
        recovery = RecoveryManager(temp_db, queue_repo, page_repo, fb_client)
        success, msg = recovery.reconcile_job(job_id)

    assert success is True
    assert "Đối chiếu thành công" in msg

    job_after = queue_repo.get_job(job_id)
    assert job_after["state"] == "published"
